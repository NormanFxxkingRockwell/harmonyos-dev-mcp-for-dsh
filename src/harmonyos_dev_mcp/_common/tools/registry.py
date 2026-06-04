"""Tool registration helpers used while importing service tool modules."""

from dataclasses import dataclass
from typing import Callable, List


@dataclass
class ToolEntry:
    """Registered tool metadata."""

    func: Callable
    category: str


_registry: List[ToolEntry] = []


def mcp_tool(category: str = "default"):
    """Register a function as an MCP tool and preserve the original callable."""

    def decorator(func: Callable) -> Callable:
        _registry.append(ToolEntry(func=func, category=category))
        func._mcp_category = category
        return func

    return decorator


def get_registered_tools() -> List[ToolEntry]:
    """Return all registered tools."""

    return list(_registry)


def get_tools_by_category(category: str) -> List[ToolEntry]:
    """Return registered tools for one category."""

    return [entry for entry in _registry if entry.category == category]


def get_tool_summary() -> dict:
    """Return total tool count and per-category counts."""

    categories: dict = {}
    for entry in _registry:
        categories[entry.category] = categories.get(entry.category, 0) + 1
    return {
        "total": len(_registry),
        "categories": categories,
    }


def clear_registry() -> None:
    """Clear the registry for tests."""

    _registry.clear()
