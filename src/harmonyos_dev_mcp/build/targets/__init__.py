"""Build target dispatch."""

from typing import Any, Optional

from .hnp import build_hnp_target
from .hsp import build_hap_with_hsp_target
from .standard import build_standard_target


def build_target(
    wrapper: Any,
    *,
    target: str,
    build_mode: str,
    product: str,
    module_name: Optional[str],
    is_clean: bool,
    include_hsp: bool,
    hsp_module_names: Optional[list[str]],
) -> dict[str, Any]:
    if target == "hnp":
        return build_hnp_target(wrapper, build_mode, product, module_name, is_clean)
    if target == "hap" and include_hsp:
        return build_hap_with_hsp_target(
            wrapper,
            build_mode,
            product,
            module_name,
            hsp_module_names,
            is_clean,
        )
    return build_standard_target(
        wrapper,
        target,
        build_mode,
        product,
        module_name,
        is_clean,
    )
