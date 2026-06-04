"""HSP target handlers."""

from pathlib import Path
from typing import Any, Optional

from loguru import logger

from .common import run_base_hap_build_for_repack


def build_hsp_outputs(
    wrapper: Any,
    build_mode: str,
    product: str,
    hsp_module_names: Optional[list[str]],
) -> dict[str, Any]:
    modules = wrapper._resolve_hsp_module_names(hsp_module_names)
    if not modules:
        modules = wrapper._discover_shared_modules()
    if not modules:
        return {
            "success": False,
            "error_code": "HSP_MODULE_NOT_FOUND",
            "stdout": "",
            "stderr": (
                "include_hsp=true requires at least one shared module. Pass hsp_module_names "
                "or add modules whose src/main/module.json5 declares "
                'type="shared".'
            ),
            "output_paths": [],
        }

    outputs: list[Path] = []
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    for module in modules:
        result = wrapper.build(
            target="hsp",
            build_mode=build_mode,
            product=product,
            module_name=module,
            is_clean=False,
            include_hsp=False,
        )
        if not result.get("success") and result.get("error_code") in {
            "BUILD_OUTPUT_NOT_FOUND",
            "STALE_BUILD_ARTIFACT",
        }:
            logger.info(f"retry HSP module build with clean because output was not refreshed: {module}")
            retry_result = wrapper.build(
                target="hsp",
                build_mode=build_mode,
                product=product,
                module_name=module,
                is_clean=True,
                include_hsp=False,
            )
            if retry_result.get("success"):
                result = retry_result
            else:
                retry_result["stdout"] = wrapper._merge_outputs(
                    result.get("stdout"),
                    retry_result.get("stdout"),
                )
                retry_result["stderr"] = wrapper._merge_outputs(
                    result.get("stderr"),
                    retry_result.get("stderr"),
                )
                result = retry_result
        stdout_parts.append(result.get("stdout", ""))
        stderr_parts.append(result.get("stderr", ""))
        if not result.get("success"):
            return {
                "success": False,
                "error_code": result.get("error_code", "HSP_BUILD_FAILED"),
                "stdout": wrapper._merge_outputs(*stdout_parts),
                "stderr": wrapper._merge_outputs(*stderr_parts),
                "output_paths": [],
            }
        output_path = result.get("output_path")
        if not output_path:
            return {
                "success": False,
                "error_code": "HSP_OUTPUT_NOT_FOUND",
                "stdout": wrapper._merge_outputs(*stdout_parts),
                "stderr": f"HSP build completed but no output path was returned for module {module}",
                "output_paths": [],
            }
        outputs.append(Path(output_path))

    return {
        "success": True,
        "stdout": wrapper._merge_outputs(*stdout_parts),
        "stderr": wrapper._merge_outputs(*stderr_parts),
        "output_paths": outputs,
    }


def build_hap_with_hsp_target(
    wrapper: Any,
    build_mode: str,
    product: str,
    module_name: Optional[str],
    hsp_module_names: Optional[list[str]],
    is_clean: bool,
) -> dict[str, Any]:
    base_result = run_base_hap_build_for_repack(
        wrapper,
        build_mode,
        product,
        module_name,
        is_clean,
        "HSP",
    )
    if not base_result.get("success"):
        return base_result

    hsp_result = build_hsp_outputs(
        wrapper,
        build_mode,
        product,
        hsp_module_names,
    )
    if not hsp_result.get("success"):
        return {
            **hsp_result,
            "stdout": wrapper._merge_outputs(base_result.get("stdout"), hsp_result.get("stdout")),
            "stderr": wrapper._merge_outputs(base_result.get("stderr"), hsp_result.get("stderr")),
            "output_path": None,
        }

    module_root = wrapper._resolve_module_root(module_name)
    signing = wrapper._resolve_repack_signing_config(product, "HSP")
    if not signing.get("success"):
        return {
            "success": False,
            "error_code": signing["error_code"],
            "stdout": wrapper._merge_outputs(base_result.get("stdout"), hsp_result.get("stdout")),
            "stderr": wrapper._merge_outputs(
                base_result.get("stderr"),
                hsp_result.get("stderr"),
                signing["stderr"],
            ),
            "output_path": None,
        }

    result = wrapper._repack_and_sign_hap_with_hsp(
        module_root,
        hsp_result["output_paths"],
        product,
        signing,
    )
    result["hsp_output_paths"] = [str(path) for path in hsp_result["output_paths"]]
    result["stdout"] = wrapper._merge_outputs(
        base_result.get("stdout"),
        hsp_result.get("stdout"),
        result.get("stdout"),
    )
    result["stderr"] = wrapper._merge_outputs(
        base_result.get("stderr"),
        hsp_result.get("stderr"),
        result.get("stderr"),
    )
    if result.get("success"):
        logger.info(f"HSP-integrated HAP build succeeded: {result['output_path']}")
    else:
        logger.error(f"HSP-integrated HAP build failed: {result.get('stderr', '')}")
    return result
