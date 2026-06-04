"""Retry helpers with exponential backoff for sync and async callables."""

import asyncio
import functools
import inspect
import time
from enum import Enum
from typing import Callable, Optional, Set, Tuple, Type

from loguru import logger


class ErrorCategory(Enum):
    """High-level error category used by retry decisions."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    UNKNOWN = "unknown"


class ErrorClassifier:
    """Classify exceptions and command result dictionaries."""

    TRANSIENT_PATTERNS: Set[str] = {
        "timeout",
        "timed out",
        "connect",
        "connection refused",
        "connection reset",
        "device not respond",
        "device not found",
        "cannot connect",
        "broken pipe",
        "resource temporarily unavailable",
        "network",
        "temporarily",
    }

    @classmethod
    def classify_error(cls, error: Exception) -> ErrorCategory:
        error_msg = str(error).lower()
        if any(pattern in error_msg for pattern in cls.TRANSIENT_PATTERNS):
            return ErrorCategory.TRANSIENT
        return ErrorCategory.UNKNOWN

    @classmethod
    def classify_result(cls, result: dict) -> ErrorCategory:
        if result.get("success"):
            return ErrorCategory.UNKNOWN

        stderr = result.get("stderr", "").lower()
        if any(pattern in stderr for pattern in cls.TRANSIENT_PATTERNS):
            return ErrorCategory.TRANSIENT
        return ErrorCategory.UNKNOWN

    @classmethod
    def is_transient(cls, error_or_result) -> bool:
        if isinstance(error_or_result, Exception):
            return cls.classify_error(error_or_result) == ErrorCategory.TRANSIENT
        if isinstance(error_or_result, dict):
            return cls.classify_result(error_or_result) == ErrorCategory.TRANSIENT
        return False


def retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    max_delay: float = 30.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    should_retry: Optional[Callable] = None,
    retry_on_transient_only: bool = False,
):
    """Retry a sync or async callable with exponential backoff."""

    def decorator(func):
        if getattr(func, "_retry_wrapped", False):
            return func

        initial_delay = max(0.0, delay)
        max_delay_sanitized = max(0.0, max_delay)
        backoff_sanitized = max(1.0, backoff)

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                current_delay = initial_delay
                last_exception = None
                last_result = None

                for attempt in range(max_retries + 1):
                    try:
                        result = await func(*args, **kwargs)
                        if should_retry and attempt < max_retries and should_retry(result):
                            logger.warning(
                                f"[Retry] {func.__name__} attempt {attempt + 1} needs retry; "
                                f"retrying in {current_delay:.1f}s"
                            )
                            await asyncio.sleep(current_delay)
                            current_delay = min(
                                current_delay * backoff_sanitized, max_delay_sanitized
                            )
                            last_result = result
                            continue
                        if attempt > 0:
                            logger.info(f"[Retry] {func.__name__} succeeded on attempt {attempt + 1}")
                        return result
                    except exceptions as e:
                        last_exception = e
                        if retry_on_transient_only and not ErrorClassifier.is_transient(e):
                            logger.error(f"[Retry] {func.__name__} permanent error, not retrying: {e}")
                            raise

                        if attempt < max_retries:
                            category = ErrorClassifier.classify_error(e).value
                            logger.warning(
                                f"[Retry] {func.__name__} attempt {attempt + 1} failed "
                                f"[{category}]: {e}; retrying in {current_delay:.1f}s"
                            )
                            await asyncio.sleep(current_delay)
                            current_delay = min(
                                current_delay * backoff_sanitized, max_delay_sanitized
                            )
                        else:
                            logger.error(
                                f"[Retry] {func.__name__} failed after {max_retries + 1} attempts: {e}"
                            )
                            raise

                if last_result is not None:
                    return last_result
                if last_exception:
                    raise last_exception
                return None

            async_wrapper._retry_wrapped = True
            return async_wrapper

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = initial_delay
            last_exception = None
            last_result = None

            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    if should_retry and attempt < max_retries and should_retry(result):
                        logger.warning(
                            f"[Retry] {func.__name__} attempt {attempt + 1} needs retry; "
                            f"retrying in {current_delay:.1f}s"
                        )
                        time.sleep(current_delay)
                        current_delay = min(
                            current_delay * backoff_sanitized, max_delay_sanitized
                        )
                        last_result = result
                        continue
                    if attempt > 0:
                        logger.info(f"[Retry] {func.__name__} succeeded on attempt {attempt + 1}")
                    return result
                except exceptions as e:
                    last_exception = e
                    if retry_on_transient_only and not ErrorClassifier.is_transient(e):
                        logger.error(f"[Retry] {func.__name__} permanent error, not retrying: {e}")
                        raise

                    if attempt < max_retries:
                        category = ErrorClassifier.classify_error(e).value
                        logger.warning(
                            f"[Retry] {func.__name__} attempt {attempt + 1} failed "
                            f"[{category}]: {e}; retrying in {current_delay:.1f}s"
                        )
                        time.sleep(current_delay)
                        current_delay = min(
                            current_delay * backoff_sanitized, max_delay_sanitized
                        )
                    else:
                        logger.error(
                            f"[Retry] {func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
                        raise

            if last_result is not None:
                return last_result
            if last_exception:
                raise last_exception
            return None

        wrapper._retry_wrapped = True
        return wrapper

    return decorator


def is_transient_error(result: dict) -> bool:
    """Return whether a command result looks retryable."""

    if result.get("success"):
        return False

    stderr = result.get("stderr", "").lower()
    return any(pattern in stderr for pattern in ErrorClassifier.TRANSIENT_PATTERNS)
