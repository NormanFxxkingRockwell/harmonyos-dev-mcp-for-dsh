"""Shared target handler helpers."""

from typing import Any, Optional

from loguru import logger


def run_base_hap_build_for_repack(
    wrapper: Any,
    build_mode: str,
    product: str,
    module_name: Optional[str],
    is_clean: bool,
    purpose: str,
) -> dict[str, Any]:
    if is_clean:
        clean_result = wrapper.clean(product=product, module_name=module_name)
        if not clean_result["success"]:
            return {
                "success": False,
                "error_code": clean_result.get("error_code", "CLEAN_FAILED"),
                "stdout": clean_result.get("stdout", ""),
                "stderr": clean_result.get("stderr", "clean failed"),
                "output_path": None,
            }

    logger.info(f"build base HAP for {purpose} packaging product={product}")
    args: list[str] = [
        "--no-daemon",
        "--mode",
        "module",
        "-p",
        f"product={product}",
        "-p",
        f"buildMode={build_mode}",
    ]
    if module_name:
        args.extend(["-p", f"module={module_name}"])
    args.extend(["assembleHap", "--analyze=normal", "--parallel", "--incremental"])
    result = wrapper._execute_command(args)
    if not result["success"]:
        result["output_path"] = None
        logger.error(f"base HAP build for {purpose} failed: {result['stderr']}")
    return result
