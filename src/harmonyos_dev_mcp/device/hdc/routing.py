"""Per-call routing context for hdc commands."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

_CURRENT_REMOTE_SERVER: ContextVar[Optional[str]] = ContextVar("current_hdc_server", default=None)


def normalize_hdc_server(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def get_hdc_server_override() -> Optional[str]:
    return normalize_hdc_server(_CURRENT_REMOTE_SERVER.get())


@contextmanager
def hdc_server_context(hdc_server: Optional[str]) -> Iterator[None]:
    token = _CURRENT_REMOTE_SERVER.set(normalize_hdc_server(hdc_server))
    try:
        yield
    finally:
        _CURRENT_REMOTE_SERVER.reset(token)
