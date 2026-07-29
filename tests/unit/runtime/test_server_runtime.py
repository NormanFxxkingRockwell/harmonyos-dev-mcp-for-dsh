import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest
from fastmcp import Client

from harmonyos_dev_mcp._common.server.base import run_server
from harmonyos_dev_mcp.runtime.server_factory import create_app, run_app
from harmonyos_dev_mcp.runtime.tool_registration import get_tool_specs, summarize_tool_specs


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


def test_explicit_tool_specs_match_public_tool_surface():
    specs = get_tool_specs()
    names = [spec.func.__name__ for spec in specs]

    assert names == [
        "build_app",
        "install_app",
        "run_app",
        "uninstall_app",
        "get_ui_tree",
        "list_windows",
        "wait_for_element",
        "list_devices",
        "query_package",
        "click",
        "long_press",
        "swipe",
        "input_text",
        "press_key",
        "find_elements",
        "screenshot",
        "drag",
        "logs_query",
    ]
    assert summarize_tool_specs(specs) == {
        "total": 18,
        "categories": {"build": 4, "e2e": 3, "general": 3, "ui": 8},
    }


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


def test_server_main_runs_the_exported_app(monkeypatch):
    from harmonyos_dev_mcp import server as server_module

    runtime_server = Mock()
    captured = {}

    monkeypatch.setattr(server_module, "mcp", runtime_server)
    monkeypatch.setattr(server_module, "run_app", lambda app: captured.setdefault("app", app))

    server_module.main()

    assert captured["app"] is runtime_server


def test_importing_package_does_not_import_server_or_register_tools():
    project_root = Path(__file__).resolve().parents[3]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(project_root / "src")
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import harmonyos_dev_mcp; "
                "print('harmonyos_dev_mcp.server' in sys.modules)"
            ),
        ],
        cwd=project_root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "False"
    assert "Registered" not in completed.stderr


@pytest.mark.asyncio
async def test_list_devices_round_trips_through_fastmcp_client(mock_hdc):
    from harmonyos_dev_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool_mcp("list_devices", {})

    assert result.isError is False
    assert isinstance(result.structuredContent, dict)
    structured = result.structuredContent
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
    assert "bundle_name" in tool_map["wait_for_element"].inputSchema["properties"]
    assert tool_map["wait_for_element"].inputSchema["properties"]["state"]["enum"] == ["found", "gone"]
    tree_result_schema = tool_map["get_ui_tree"].outputSchema["properties"]["result"]["anyOf"][0]
    window_id_schema = tree_result_schema["properties"]["window_id"]
    assert {option["type"] for option in window_id_schema["anyOf"]} == {"integer", "null"}


@pytest.mark.asyncio
async def test_all_tools_expose_agent_facing_descriptions_and_input_contracts(mock_hdc):
    from harmonyos_dev_mcp.server import mcp

    async with Client(mcp) as client:
        tools = await client.list_tools()

    tool_map = {tool.name: tool for tool in tools}

    assert all(tool.description and tool.description.strip() for tool in tools)
    assert all(tool.outputSchema is not None for tool in tools)
    assert tool_map["press_key"].inputSchema["required"] == ["key"]
    modifier_schema = tool_map["press_key"].inputSchema["properties"]["modifiers"]
    modifier_items = next(
        option["items"]
        for option in modifier_schema["anyOf"]
        if option.get("type") == "array"
    )
    assert modifier_items["enum"] == ["Ctrl", "Alt", "Shift", "Meta"]
    assert "every official HarmonyOS" in tool_map["press_key"].description
    press_result_schema = tool_map["press_key"].outputSchema["properties"]["result"]["anyOf"][0]
    assert set(press_result_schema["properties"]) >= {
        "key",
        "key_code",
        "modifiers",
        "event_key_codes",
        "dispatched",
        "effect_verified",
    }
    assert tool_map["input_text"].inputSchema["required"] == ["text"]
    assert tool_map["input_text"].inputSchema["properties"]["mode"]["default"] == "replace"
    assert "element_handle" in tool_map["input_text"].description
    assert "verified=false" in tool_map["input_text"].description
    input_result_schema = tool_map["input_text"].outputSchema["properties"]["result"]["anyOf"][0]
    assert set(input_result_schema["properties"]) >= {
        "requested_text",
        "before_text",
        "input_strategy",
        "dispatched",
        "verified",
        "clipboard_modified",
        "actual_text",
        "stage",
    }
    assert "find_element" not in tool_map
    assert "wait_element" not in tool_map
    assert tool_map["click"].inputSchema["properties"]["count"]["enum"] == [1, 2]
    assert "click_element" not in tool_map
    assert "long_press_element" not in tool_map
    handle_schema = tool_map["input_text"].inputSchema["properties"]["element_handle"]
    assert any(option.get("type") == "object" for option in handle_schema["anyOf"])


@pytest.mark.asyncio
async def test_tool_errors_are_not_double_wrapped_and_set_mcp_error_state(mock_hdc):
    from harmonyos_dev_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool_mcp("press_key", {"key": 65535})

    assert result.isError is True
    assert result.structuredContent["tool"] == "press_key"
    assert result.structuredContent["ok"] is False
    assert result.structuredContent["error"]["code"] == "INVALID_KEY"
    assert "structuredContent" not in result.structuredContent
