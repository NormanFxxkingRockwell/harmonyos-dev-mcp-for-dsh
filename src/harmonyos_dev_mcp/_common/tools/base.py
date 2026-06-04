"""Shared base helpers for MCP tool implementations."""

import functools
import inspect
import os

from loguru import logger


class ToolBase:
    """Common validation and error wrapping helpers."""

    @staticmethod
    def wrap_error(error: Exception, error_code: str = None) -> dict:
        """Wrap an exception in the standard structured error shape."""

        logger.error(f"operation failed: {error}")

        code = error_code or getattr(error, "code", "UNKNOWN_ERROR")
        return {
            "tool": "unknown",
            "ok": False,
            "result": {},
            "error": {
                "code": code,
                "detail": str(error),
            },
            "meta": {},
        }

    @staticmethod
    def format_duration(seconds: float) -> str:
        """Format a duration in milliseconds, seconds, or minutes."""

        if seconds < 1:
            return f"{seconds * 1000:.0f}ms"
        if seconds < 60:
            return f"{seconds:.2f}s"
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"

    @staticmethod
    def validate_path(path: str) -> bool:
        """Validate a path string against null bytes and parent traversal."""

        if "\x00" in path:
            raise ValueError(f"path contains a null byte: {path!r}")
        normalized = os.path.normpath(path)
        if ".." in normalized.split(os.sep):
            raise ValueError(f"path contains parent traversal: {path!r}")
        return True

    @staticmethod
    def validate_params(**param_rules):
        """Validate decorated function keyword arguments by named rules."""

        def decorator(func):
            def _do_validate(kwargs):
                for param_name, rules in param_rules.items():
                    value = kwargs.get(param_name)
                    if value is None:
                        continue
                    for rule in rules:
                        if rule == "path" and isinstance(value, str):
                            ToolBase.validate_path(value)
                        elif rule == "nonempty":
                            if not value:
                                raise ValueError(f"parameter {param_name!r} must not be empty")
                        elif rule.startswith("max_length:"):
                            max_len = int(rule.split(":")[1])
                            if isinstance(value, str) and len(value) > max_len:
                                raise ValueError(
                                    f"parameter {param_name!r} length {len(value)} exceeds {max_len}"
                                )
                        elif rule.startswith("int_range:"):
                            parts = rule.split(":")[1].split(",")
                            lo, hi = int(parts[0]), int(parts[1])
                            if isinstance(value, int) and not (lo <= value <= hi):
                                raise ValueError(
                                    f"parameter {param_name!r} value {value} is outside [{lo}, {hi}]"
                                )

            if inspect.iscoroutinefunction(func):

                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    _do_validate(kwargs)
                    return await func(*args, **kwargs)

                return async_wrapper

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                _do_validate(kwargs)
                return func(*args, **kwargs)

            return sync_wrapper

        return decorator

    @staticmethod
    def handle_tool_error(error_code: str, **default_fields):
        """Wrap sync or async tool functions with standard error handling."""

        def decorator(func):
            if inspect.iscoroutinefunction(func):

                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        error_result = ToolBase.wrap_error(e, error_code)
                        error_result["tool"] = func.__name__
                        for k, v in default_fields.items():
                            error_result.setdefault("result", {})
                            error_result["result"].setdefault(k, v)
                        return error_result

                return async_wrapper

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_result = ToolBase.wrap_error(e, error_code)
                    error_result["tool"] = func.__name__
                    for k, v in default_fields.items():
                        error_result.setdefault("result", {})
                        error_result["result"].setdefault(k, v)
                    return error_result

            return wrapper

        return decorator
