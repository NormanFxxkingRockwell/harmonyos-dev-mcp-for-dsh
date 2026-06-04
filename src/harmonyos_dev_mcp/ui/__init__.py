"""UI automation internals."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .operations import UiTestWrapper
    from .tree_parser import UITreeParser

__all__ = ["UiTestWrapper", "UITreeParser"]


def __getattr__(name: str) -> Any:
    if name == "UiTestWrapper":
        from .operations import UiTestWrapper

        return UiTestWrapper
    if name == "UITreeParser":
        from .tree_parser import UITreeParser

        return UITreeParser
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
