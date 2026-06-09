import functools
import inspect
from typing import Any, Optional

from loguru import logger

from harmonyos_dev_mcp._common.tools.base import ToolBase
from harmonyos_dev_mcp._common.tools.response import error_result
from harmonyos_dev_mcp.config import Config
from harmonyos_dev_mcp.device.hdc.routing import get_hdc_server_override, hdc_server_context


class DeviceToolSupport(ToolBase):
    REMOTE_SERVER_PARAM = "hdc_server"

    @staticmethod
    def build_device_error(code: str, detail: str, **result_fields):
        return error_result(code, detail, result=result_fields, tool="with_device")

    @staticmethod
    def get_device_id(device_id: Optional[str] = None):
        if device_id:
            return True, device_id, None

        Config.ensure_init()
        route_ip = get_hdc_server_override() or Config.HARMONYOS_HDC_SERVER
        if route_ip:
            return True, route_ip, None

        if Config.DEFAULT_DEVICE_ID:
            return True, Config.DEFAULT_DEVICE_ID, None

        try:
            from ..container import get_hdc

            hdc = get_hdc()
            devices = hdc.list_devices()
            if not devices:
                return False, None, DeviceToolSupport.build_device_error("DEVICE_NOT_FOUND", "No device found")
            return True, devices[0], None
        except Exception as exc:
            logger.error(f"Failed to get device list: {exc}")
            return False, None, DeviceToolSupport.build_device_error("DEVICE_LIST_ERROR", str(exc))

    @staticmethod
    def _add_hdc_server_signature(wrapper, func):
        signature = inspect.signature(func)
        if DeviceToolSupport.REMOTE_SERVER_PARAM in signature.parameters:
            wrapper.__signature__ = signature
            return wrapper

        hdc_server = inspect.Parameter(
            DeviceToolSupport.REMOTE_SERVER_PARAM,
            inspect.Parameter.KEYWORD_ONLY,
            default=None,
            annotation=Optional[str],
        )
        parameters = list(signature.parameters.values())
        insert_at = len(parameters)
        for index, parameter in enumerate(parameters):
            if parameter.kind is inspect.Parameter.VAR_KEYWORD:
                insert_at = index
                break
        parameters.insert(insert_at, hdc_server)
        updated_signature = signature.replace(parameters=parameters)
        wrapper.__signature__ = updated_signature
        annotations = dict(getattr(func, "__annotations__", {}))
        annotations[DeviceToolSupport.REMOTE_SERVER_PARAM] = Optional[str]
        for parameter in updated_signature.parameters.values():
            if parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                annotations.setdefault(parameter.name, Any)
        wrapper.__annotations__ = annotations
        return wrapper

    @staticmethod
    def with_device(**error_fields):
        def decorator(func):
            if inspect.iscoroutinefunction(func):

                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    hdc_server = kwargs.pop(DeviceToolSupport.REMOTE_SERVER_PARAM, None)
                    device_id = kwargs.get("device_id")
                    with hdc_server_context(hdc_server):
                        ok, resolved_device, device_error = DeviceToolSupport.get_device_id(device_id)
                        if not ok:
                            device = device_error or DeviceToolSupport.build_device_error(
                                "DEVICE_NOT_FOUND",
                                "No device found",
                            )
                            for key, value in error_fields.items():
                                device.setdefault("result", {})
                                device["result"].setdefault(key, value)
                            return device
                        kwargs["device_id"] = resolved_device
                        return await func(*args, **kwargs)

                return DeviceToolSupport._add_hdc_server_signature(async_wrapper, func)

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                hdc_server = kwargs.pop(DeviceToolSupport.REMOTE_SERVER_PARAM, None)
                device_id = kwargs.get("device_id")
                with hdc_server_context(hdc_server):
                    ok, resolved_device, device_error = DeviceToolSupport.get_device_id(device_id)
                    if not ok:
                        device = device_error or DeviceToolSupport.build_device_error(
                            "DEVICE_NOT_FOUND",
                            "No device found",
                        )
                        for key, value in error_fields.items():
                            device.setdefault("result", {})
                            device["result"].setdefault(key, value)
                        return device
                    kwargs["device_id"] = resolved_device
                    return func(*args, **kwargs)

            return DeviceToolSupport._add_hdc_server_signature(wrapper, func)

        return decorator
