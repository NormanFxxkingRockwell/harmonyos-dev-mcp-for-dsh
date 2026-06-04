"""Application server factory and runtime bootstrap."""

from typing import Any, Optional

from loguru import logger

from harmonyos_dev_mcp._common.server.base import create_server, run_server
from harmonyos_dev_mcp._common.utils.logger import setup_logger
from harmonyos_dev_mcp.config import Config


def import_tool_modules() -> None:
    from harmonyos_dev_mcp.tools import build, e2e, general, ui  # noqa: F401
    from harmonyos_dev_mcp.tools.log.query import logs_query  # noqa: F401


def create_app(name: str = "harmonyos-tools") -> Any:
    import_tool_modules()
    return create_server(name)


def setup_runtime_logger() -> None:
    setup_logger(app_name="harmonyos_dev_mcp", log_level=Config.LOG_LEVEL)


def on_startup() -> None:
    from harmonyos_dev_mcp.container import get_hdc

    try:
        hdc = get_hdc()
        devices = hdc.list_devices()
        logger.info(f"Detected {len(devices)} device(s)")
    except Exception as exc:
        logger.warning(f"Device detection failed: {exc}")


def run_app(server: Optional[Any] = None) -> None:
    run_server(
        server or create_app(),
        config_class=Config,
        setup_logger_func=setup_runtime_logger,
        on_startup=on_startup,
    )
