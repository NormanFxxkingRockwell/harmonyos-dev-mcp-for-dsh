"""Tests for E2E-oriented wait tools."""

import asyncio
import time
from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
class TestWaitTools:
    async def test_wait_for_element_returns_first_match(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result, monkeypatch
    ):
        from harmonyos_dev_mcp.tools import e2e
        monkeypatch.setattr(e2e, "get_ui_operations", lambda: mock_ui_operations)

        sc = unwrap_result(await e2e.wait_for_element(text="Button", state="found", timeout_ms=100, interval_ms=1))

        assert sc["ok"] is True
        assert sc["result"]["state"] == "found"
        assert sc["result"]["satisfied"] is True
        assert sc["result"]["element"]["id"] == "btn_login"
        assert sc["result"]["element"]["bounds"]["left"] == 80

    async def test_wait_for_element_found_times_out(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result, monkeypatch
    ):
        from harmonyos_dev_mcp.tools import e2e
        monkeypatch.setattr(e2e, "get_ui_operations", lambda: mock_ui_operations)

        mock_ui_operations.find_element.return_value = {"success": True, "window_id": 1, "elements": [], "count": 0}

        sc = unwrap_result(await e2e.wait_for_element(text="missing", state="found", timeout_ms=0, interval_ms=0))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "WAIT_TIMEOUT"

    async def test_wait_for_element_gone_succeeds_when_missing(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result, monkeypatch
    ):
        from harmonyos_dev_mcp.tools import e2e
        monkeypatch.setattr(e2e, "get_ui_operations", lambda: mock_ui_operations)

        mock_ui_operations.find_element.return_value = {"success": True, "window_id": 1, "elements": [], "count": 0}

        sc = unwrap_result(await e2e.wait_for_element(text="toast", state="gone", timeout_ms=100, interval_ms=1))

        assert sc["ok"] is True
        assert sc["result"]["state"] == "gone"
        assert sc["result"]["satisfied"] is True

    async def test_wait_for_element_gone_times_out_when_element_still_present(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result, monkeypatch
    ):
        from harmonyos_dev_mcp.tools import e2e
        monkeypatch.setattr(e2e, "get_ui_operations", lambda: mock_ui_operations)

        sc = unwrap_result(await e2e.wait_for_element(text="toast", state="gone", timeout_ms=0, interval_ms=0))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "WAIT_TIMEOUT"

    async def test_wait_for_element_rejects_invalid_state(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result, monkeypatch
    ):
        from harmonyos_dev_mcp.tools import e2e
        monkeypatch.setattr(e2e, "get_ui_operations", lambda: mock_ui_operations)

        sc = unwrap_result(await e2e.wait_for_element(text="toast", state="bad", timeout_ms=0, interval_ms=0))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "INVALID_WAIT_STATE"

    async def test_wait_for_element_rejects_negative_timeout(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result, monkeypatch
    ):
        from harmonyos_dev_mcp.tools import e2e
        monkeypatch.setattr(e2e, "get_ui_operations", lambda: mock_ui_operations)

        sc = unwrap_result(await e2e.wait_for_element(text="toast", timeout_ms=-1, interval_ms=0))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "INVALID_TIMEOUT"

    async def test_wait_for_element_rejects_negative_interval(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result, monkeypatch
    ):
        from harmonyos_dev_mcp.tools import e2e
        monkeypatch.setattr(e2e, "get_ui_operations", lambda: mock_ui_operations)

        sc = unwrap_result(await e2e.wait_for_element(text="toast", timeout_ms=0, interval_ms=-1))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "INVALID_INTERVAL"

    async def test_wait_for_element_found_requires_stable_second_observation(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result, monkeypatch
    ):
        from harmonyos_dev_mcp.tools import e2e
        monkeypatch.setattr(e2e, "get_ui_operations", lambda: mock_ui_operations)

        mock_ui_operations.find_element.side_effect = [
            {"success": True, "window_id": 1, "elements": [{"id": "btn_login", "x": 100, "y": 200}], "count": 1},
            {"success": True, "window_id": 1, "elements": [], "count": 0},
            {"success": True, "window_id": 1, "elements": [{"id": "btn_login", "x": 100, "y": 200}], "count": 1},
            {"success": True, "window_id": 1, "elements": [{"id": "btn_login", "x": 100, "y": 200}], "count": 1},
        ]

        sc = unwrap_result(await e2e.wait_for_element(text="Button", state="found", timeout_ms=50, interval_ms=1))

        assert sc["ok"] is True
        assert sc["result"]["satisfied"] is True

    async def test_wait_for_element_gone_requires_stable_second_observation(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result, monkeypatch
    ):
        from harmonyos_dev_mcp.tools import e2e
        monkeypatch.setattr(e2e, "get_ui_operations", lambda: mock_ui_operations)

        mock_ui_operations.find_element.side_effect = [
            {"success": True, "window_id": 1, "elements": [], "count": 0},
            {"success": True, "window_id": 1, "elements": [{"id": "toast", "x": 100, "y": 200}], "count": 1},
            {"success": True, "window_id": 1, "elements": [], "count": 0},
            {"success": True, "window_id": 1, "elements": [], "count": 0},
        ]

        sc = unwrap_result(await e2e.wait_for_element(text="toast", state="gone", timeout_ms=50, interval_ms=1))

        assert sc["ok"] is True
        assert sc["result"]["state"] == "gone"

    async def test_wait_for_element_bounds_stability_check_by_wall_clock_timeout(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result, monkeypatch
    ):
        from harmonyos_dev_mcp.tools import e2e

        monkeypatch.setattr(e2e, "get_ui_operations", lambda: mock_ui_operations)
        calls = 0

        async def find_elements_once(**_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return {
                    "success": True,
                    "window_id": 1,
                    "elements": [{"id": "btn_login", "x": 100, "y": 200}],
                    "count": 1,
                }
            await asyncio.sleep(0.2)
            return {
                "success": True,
                "window_id": 1,
                "elements": [{"id": "btn_login", "x": 100, "y": 200}],
                "count": 1,
            }

        monkeypatch.setattr(e2e, "_find_elements_once", find_elements_once)

        started = time.monotonic()
        sc = unwrap_result(
            await e2e.wait_for_element(
                text="Button",
                state="found",
                timeout_ms=20,
                interval_ms=1,
            )
        )
        elapsed = time.monotonic() - started

        assert sc["ok"] is False
        assert sc["error"]["code"] == "WAIT_TIMEOUT"
        assert sc["result"]["elapsed_ms"] >= 20
        assert elapsed < 0.1

    async def test_wait_for_element_zero_timeout_skips_device_query(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result, monkeypatch
    ):
        from harmonyos_dev_mcp.tools import e2e

        monkeypatch.setattr(e2e, "get_ui_operations", lambda: mock_ui_operations)

        sc = unwrap_result(
            await e2e.wait_for_element(
                text="Button",
                state="found",
                timeout_ms=0,
                interval_ms=0,
            )
        )

        assert sc["ok"] is False
        assert sc["error"]["code"] == "WAIT_TIMEOUT"
        mock_ui_operations.find_element.assert_not_called()
