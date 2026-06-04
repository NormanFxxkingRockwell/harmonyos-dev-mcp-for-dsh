"""Standard hvigor target handlers."""
from pathlib import Path
from typing import Any, Optional

from loguru import logger


def build_standard_target(
    wrapper: Any,
    target: str,
    build_mode: str,
    product: str,
    module_name: Optional[str],
    is_clean: bool,
) -> dict[str, Any]:
    build_started_at = wrapper._now()
    if is_clean:
        clean_result = wrapper.clean(
            product=product,
            module_name=module_name if target in {"hap", "har", "hsp"} else None,
        )
        if not clean_result["success"]:
            return {
                "success": False,
                "error_code": clean_result.get("error_code", "CLEAN_FAILED"),
                "stdout": clean_result.get("stdout", ""),
                "stderr": clean_result.get("stderr", "clean failed"),
                "output_path": None,
            }

    logger.info(f"build {target.upper()} for product={product}")
    args: list[str] = ["--no-daemon"]
    if target in {"hap", "har", "hsp"}:
        args.extend(["--mode", "module"])
    args.extend(["-p", f"product={product}", "-p", f"buildMode={build_mode}"])
    if target in {"har", "hsp"} and module_name:
        args.extend(["-p", f"module={module_name}"])
    args.extend(
        [
            {"hap": "assembleHap", "har": "assembleHar", "hsp": "assembleHsp", "app": "assembleApp"}[target],
            "--analyze=normal",
            "--parallel",
            "--incremental",
        ]
    )
    result = wrapper._execute_command(args)
    if result["success"]:
        return _resolve_successful_output(
            wrapper,
            result,
            target,
            build_mode,
            product,
            module_name,
            build_started_at,
        )

    result["output_path"] = None
    logger.error(f"{target.upper()} build failed: {result['stderr']}")
    return result


def _resolve_successful_output(
    wrapper: Any,
    result: dict[str, Any],
    target: str,
    build_mode: str,
    product: str,
    module_name: Optional[str],
    build_started_at: float,
) -> dict[str, Any]:
    logged_output = None
    artifact_source = ""
    sign_status = "unknown"
    output_path = wrapper._find_output_from_metadata(target, product, module_name, not_before=build_started_at)
    if output_path is not None:
        artifact_source = "metadata"
        sign_status = wrapper._resolve_sign_status(output_path)
    if output_path is None:
        logged_output = wrapper._extract_output_path_from_logs(
            result.get("stdout", ""),
            result.get("stderr", ""),
            target,
        )
        output_path = wrapper._extract_output_path_from_logs(
            result.get("stdout", ""),
            result.get("stderr", ""),
            target,
            not_before=build_started_at,
        )
        if output_path is not None:
            artifact_source = "logs"
            sign_status = wrapper._resolve_sign_status(output_path)
    if output_path is None:
        output_path = wrapper._find_build_output(
            target,
            build_mode,
            product,
            module_name,
            not_before=build_started_at,
        )
        if output_path is not None:
            artifact_source = "scan"
            sign_status = wrapper._resolve_sign_status(output_path)
    if output_path is None and logged_output is not None and not wrapper._is_fresh_output(logged_output, build_started_at):
        return {
            "success": False,
            "error_code": "STALE_BUILD_ARTIFACT",
            "stdout": result.get("stdout", ""),
            "stderr": wrapper._build_output_resolution_guidance(stale_logged_output=True),
            "output_path": None,
        }
    if output_path is None:
        output_path = wrapper._find_build_output(
            target,
            build_mode,
            product,
            module_name,
        )
        if output_path is not None:
            artifact_source = "cached_scan"
            sign_status = wrapper._resolve_sign_status(output_path)
    if output_path is None:
        return {
            "success": False,
            "error_code": "BUILD_OUTPUT_NOT_FOUND",
            "stdout": result.get("stdout", ""),
            "stderr": wrapper._build_output_resolution_guidance(),
            "output_path": None,
        }
    if target == "hap" and output_path is not None and "unsigned" in output_path.name.lower():
        fallback_result = wrapper._run_sign_fallback(build_mode)
        if fallback_result["success"]:
            output_path = Path(fallback_result["output_path"])
            result["stdout"] = f"{result.get('stdout', '')}\n{fallback_result.get('stdout', '')}".strip()
            result["stderr"] = f"{result.get('stderr', '')}\n{fallback_result.get('stderr', '')}".strip()
            artifact_source = fallback_result.get("artifact_source", "sign_fallback")
            sign_status = "signed"
        elif fallback_result.get("error_code") != "SIGN_FALLBACK_SCRIPT_MISSING":
            return {
                "success": False,
                "error_code": fallback_result["error_code"],
                "stdout": f"{result.get('stdout', '')}\n{fallback_result.get('stdout', '')}".strip(),
                "stderr": (
                    f"{result.get('stderr', '')}\n{fallback_result.get('stderr', '')}"
                ).strip(),
                "output_path": None,
            }
    result["output_path"] = str(output_path) if output_path else None
    result["artifact_source"] = artifact_source or None
    result["sign_status"] = sign_status
    logger.info(f"{target.upper()} build succeeded: {result['output_path']}")
    return result
