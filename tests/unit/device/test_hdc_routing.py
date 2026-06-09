import inspect

import pytest

from harmonyos_dev_mcp.config import Config
from harmonyos_dev_mcp.device.hdc.hdc_app import HdcApp
from harmonyos_dev_mcp.device.hdc.hdc_base import HdcBase
from harmonyos_dev_mcp.device.hdc.hdc_device import HdcDevice
from harmonyos_dev_mcp.device.hdc.hdc_file import HdcFile
from harmonyos_dev_mcp.device.hdc.routing import get_hdc_server_override, hdc_server_context
from harmonyos_dev_mcp.tools.device_support import DeviceToolSupport


class _RoutingHdc(HdcBase, HdcDevice, HdcFile, HdcApp):
    def __init__(self, result=None):
        self.hdc_path = "hdc"
        self.calls = []
        self._result = result or {
            "success": True,
            "stdout": "",
            "stderr": "",
            "returncode": 0,
        }

    def _execute_command(self, args, timeout=None, cwd=None):
        self.calls.append({"args": args, "timeout": timeout, "cwd": cwd})
        return dict(self._result)


@pytest.fixture(autouse=True)
def reset_hdc_routing_config(monkeypatch):
    monkeypatch.setattr(Config, "HARMONYOS_HDC_SERVER", None)


def test_existing_shell_command_keeps_target_flag():
    hdc = _RoutingHdc()

    result = hdc.execute_shell("device_001", "param get const.product.model")

    assert result["success"] is True
    assert hdc.calls[-1]["args"] == ["-t", "device_001", "shell", "param get const.product.model"]


def test_shell_command_adds_route_after_sn_target():
    Config.HARMONYOS_HDC_SERVER = "192.168.43.10:8710"
    hdc = _RoutingHdc()

    hdc.execute_shell("SN123", "param get const.product.model")

    assert hdc.calls[-1]["args"] == [
        "-t",
        "SN123",
        "-s",
        "192.168.43.10:8710",
        "shell",
        "param get const.product.model",
    ]


def test_context_server_is_used_without_changing_device_target():
    hdc = _RoutingHdc()

    with hdc_server_context("10.0.0.8:8710"):
        hdc.uninstall_app("SN123", "com.example.app")

    assert hdc.calls[-1]["args"] == [
        "-t",
        "SN123",
        "-s",
        "10.0.0.8:8710",
        "uninstall",
        "com.example.app",
    ]


def test_list_devices_returns_configured_ip_target_without_hdc_list_call():
    Config.HARMONYOS_HDC_SERVER = "10.0.0.8:8710"
    hdc = _RoutingHdc()

    assert hdc.list_devices() == ["10.0.0.8:8710"]
    assert hdc.calls == []


def test_ip_server_and_sn_target_are_combined_without_connect_probe():
    hdc = _RoutingHdc()

    with hdc_server_context("192.168.43.34:35215"):
        hdc.execute_shell("SN123", "param get const.product.model")

    assert hdc.calls == [
        {
            "args": [
                "-t",
                "SN123",
                "-s",
                "192.168.43.34:35215",
                "shell",
                "param get const.product.model",
            ],
            "timeout": None,
            "cwd": None,
        }
    ]


def test_device_id_is_only_used_as_target_without_connect_probe():
    hdc = _RoutingHdc()

    hdc.execute_shell("SN123", "param get const.product.name")

    assert hdc.calls == [
        {
            "args": [
                "-t",
                "SN123",
                "shell",
                "param get const.product.name",
            ],
            "timeout": None,
            "cwd": None,
        }
    ]


def test_realtime_logs_keep_shell_after_target_and_route_flags():
    hdc = _RoutingHdc({"success": True, "stdout": "line-1", "stderr": "", "returncode": 0})

    with hdc_server_context("192.168.43.34:35215"):
        text = hdc.get_realtime_logs("SN123")

    assert text == "line-1"
    assert hdc.calls[-1]["args"] == [
        "-t",
        "SN123",
        "-s",
        "192.168.43.34:35215",
        "shell",
        "hilog -x",
    ]


def test_configured_ip_only_is_used_as_target_for_list_devices():
    Config.HARMONYOS_HDC_SERVER = "192.168.43.34:35215"
    hdc = _RoutingHdc()

    devices = hdc.list_devices()

    assert devices == ["192.168.43.34:35215"]
    assert hdc.calls == []


def test_configured_ip_only_shell_uses_target_flag():
    Config.HARMONYOS_HDC_SERVER = "192.168.43.34:35215"
    hdc = _RoutingHdc()

    hdc.execute_shell(None, "param get const.product.name")

    assert hdc.calls[-1]["args"] == [
        "-t",
        "192.168.43.34:35215",
        "shell",
        "param get const.product.name",
    ]


@pytest.mark.asyncio
async def test_with_device_accepts_hdc_server_as_existing_tool_parameter():
    seen = {}

    @DeviceToolSupport.with_device()
    async def sample_tool(device_id=None):
        seen["device_id"] = device_id
        seen["hdc_server"] = get_hdc_server_override()
        return {"ok": True}

    assert "hdc_server" in inspect.signature(sample_tool).parameters

    await sample_tool(device_id="SN123", hdc_server="10.0.0.8:8710")

    assert seen == {"device_id": "SN123", "hdc_server": "10.0.0.8:8710"}


@pytest.mark.asyncio
async def test_with_device_maps_ip_only_calls_to_target():
    seen = {}

    @DeviceToolSupport.with_device()
    async def sample_tool(device_id=None):
        seen["device_id"] = device_id
        seen["hdc_server"] = get_hdc_server_override()
        return {"ok": True}

    await sample_tool(hdc_server="10.0.0.8:8710")

    assert seen == {"device_id": "10.0.0.8:8710", "hdc_server": "10.0.0.8:8710"}


def test_get_device_id_maps_configured_ip_to_target():
    Config.HARMONYOS_HDC_SERVER = "10.0.0.8:8710"

    ok, resolved_device, device_error = DeviceToolSupport.get_device_id(None)

    assert ok is True
    assert resolved_device == "10.0.0.8:8710"
    assert device_error is None
