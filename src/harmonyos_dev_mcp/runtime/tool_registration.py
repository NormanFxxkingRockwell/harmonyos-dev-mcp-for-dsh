"""Explicit MCP tool registration."""

from dataclasses import dataclass
from typing import Callable, Optional

from fastmcp import FastMCP
from loguru import logger

from harmonyos_dev_mcp._common.server.base import _wrap_with_error_handler


@dataclass(frozen=True)
class ToolSpec:
    func: Callable
    category: str


def get_tool_specs() -> tuple[ToolSpec, ...]:
    from harmonyos_dev_mcp.tools import build, e2e, general, ui
    from harmonyos_dev_mcp.tools.log.query import logs_query

    return (
        ToolSpec(build.build_app, "build"),
        ToolSpec(build.install_app, "build"),
        ToolSpec(build.run_app, "build"),
        ToolSpec(build.uninstall_app, "build"),
        ToolSpec(e2e.get_ui_tree, "e2e"),
        ToolSpec(e2e.list_windows, "e2e"),
        ToolSpec(e2e.wait_element, "e2e"),
        ToolSpec(general.list_devices, "general"),
        ToolSpec(general.query_package, "general"),
        ToolSpec(ui.click_element, "ui"),
        ToolSpec(ui.long_press_element, "ui"),
        ToolSpec(ui.swipe, "ui"),
        ToolSpec(ui.input_text, "ui"),
        ToolSpec(ui.press_key, "ui"),
        ToolSpec(ui.find_element, "ui"),
        ToolSpec(ui.screenshot, "ui"),
        ToolSpec(ui.drag, "ui"),
        ToolSpec(logs_query, "general"),
    )


def summarize_tool_specs(tool_specs: tuple[ToolSpec, ...]) -> dict:
    categories: dict[str, int] = {}
    for spec in tool_specs:
        categories[spec.category] = categories.get(spec.category, 0) + 1
    return {
        "total": len(tool_specs),
        "categories": categories,
    }


def register_tools(
    server: FastMCP,
    *,
    enable_error_handler: bool = True,
    on_error: Optional[Callable] = None,
) -> tuple[Callable, ...]:
    registered_tools = []
    tool_specs = get_tool_specs()
    for spec in tool_specs:
        func = spec.func
        if enable_error_handler:
            func = _wrap_with_error_handler(func, on_error)
        server.tool(output_schema=None)(func)
        registered_tools.append(func)

    registered = tuple(registered_tools)
    server.codex_registered_tools = registered
    summary = summarize_tool_specs(tool_specs)
    logger.info(f"Registered {summary['total']} tools, categories: {summary['categories']}")
    return registered
