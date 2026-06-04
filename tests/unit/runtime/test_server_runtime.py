from unittest.mock import Mock

import pytest
from fastmcp import Client

from harmonyos_dev_mcp._common.server.base import run_server
from harmonyos_dev_mcp.runtime.server_factory import create_app, run_app


def test_run_server_disables_banner_by_default():
    server = Mock()

    run_server(server)

    server.run.assert_called_once_with(show_banner=False)


def test_run_server_allows_overriding_banner():
    server = Mock()

    run_server(server, show_banner=True)

    server.run.assert_called_once_with(show_banner=True)


def test_create_app_returns_isolated_servers_with_same_tools():
    first = create_app()
    second = create_app()

    assert first is not second
    first_tools = tuple(func.__name__ for func in first.codex_registered_tools)
    second_tools = tuple(func.__name__ for func in second.codex_registered_tools)
    assert len(first_tools) == 18
    assert first_tools == second_tools


def test_run_app_uses_provided_server(monkeypatch):
    server = Mock()
    captured = {}

    def fake_run_server(server_arg, **kwargs):
        captured["server"] = server_arg
        captured["kwargs"] = kwargs

    monkeypatch.setattr("harmonyos_dev_mcp.runtime.server_factory.run_server", fake_run_server)

    run_app(server)

    assert captured["server"] is server
    assert captured["kwargs"]["config_class"].__name__ == "Config"
    assert callable(captured["kwargs"]["setup_logger_func"])
    assert callable(captured["kwargs"]["on_startup"])


def test_server_main_creates_app_at_runtime(monkeypatch):
    from harmonyos_dev_mcp import server as server_module

    runtime_server = Mock()
    captured = {}

    monkeypatch.setattr(server_module, "create_app", lambda: runtime_server)
    monkeypatch.setattr(server_module, "run_app", lambda app: captured.setdefault("app", app))

    server_module.main()

    assert captured["app"] is runtime_server


@pytest.mark.asyncio
async def test_list_devices_round_trips_through_fastmcp_client(mock_hdc):
    from harmonyos_dev_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool_mcp("list_devices", {})

    assert result.isError is False
    assert isinstance(result.structuredContent, dict)
    structured = result.structuredContent
    if "structuredContent" in structured:
        structured = structured["structuredContent"]
    assert structured["ok"] is True
    assert structured["result"]["count"] == len(structured["result"]["devices"])
    assert structured["result"]["devices"]
    assert structured["result"]["devices"][0]["device_id"]


@pytest.mark.asyncio
async def test_e2e_tool_schemas_are_exposed_via_fastmcp(mock_hdc):
    from harmonyos_dev_mcp.server import mcp

    async with Client(mcp) as client:
        tools = await client.list_tools()

    tool_map = {tool.name: tool for tool in tools}

    assert "bundle_name" in tool_map["list_windows"].inputSchema["properties"]
    assert "bundle_name" in tool_map["get_ui_tree"].inputSchema["properties"]
    assert "bundle_name" in tool_map["wait_element"].inputSchema["properties"]
    assert tool_map["wait_element"].inputSchema["properties"]["state"]["enum"] == ["found", "gone"]
