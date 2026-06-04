"""HNP target handler."""

from typing import Any, Optional

from loguru import logger

from .common import run_base_hap_build_for_repack


def build_hnp_target(
    wrapper: Any,
    build_mode: str,
    product: str,
    module_name: Optional[str],
    is_clean: bool,
) -> dict[str, Any]:
    base_result = run_base_hap_build_for_repack(
        wrapper,
        build_mode,
        product,
        module_name,
        is_clean,
        "HNP",
    )
    if not base_result.get("success"):
        return base_result

    module_root = wrapper._resolve_module_root(module_name)
    hnp_source_root = wrapper._find_hnp_source_root(module_root)
    if hnp_source_root is None:
        return {
            "error_code": "HNP_PACKAGE_NOT_FOUND",
            "stdout": base_result.get("stdout", ""),
            "stderr": (
                "target=hnp requires built HNP packages under a module hnp directory, "
                f"for example {module_root / 'hnp'} containing ABI subdirectories with .hnp files"
            ),
            "success": False,
            "output_path": None,
        }

    signing = wrapper._resolve_repack_signing_config(product, "HNP")
    if not signing.get("success"):
        return {
            "success": False,
            "error_code": signing["error_code"],
            "stdout": base_result.get("stdout", ""),
            "stderr": wrapper._merge_outputs(base_result.get("stderr"), signing["stderr"]),
            "output_path": None,
        }

    result = wrapper._repack_and_sign_hnp(module_root, hnp_source_root, product, signing)
    result["stdout"] = wrapper._merge_outputs(base_result.get("stdout"), result.get("stdout"))
    result["stderr"] = wrapper._merge_outputs(base_result.get("stderr"), result.get("stderr"))
    if result.get("success"):
        logger.info(f"HNP build succeeded: {result['output_path']}")
    else:
        logger.error(f"HNP build failed: {result.get('stderr', '')}")

    return result
