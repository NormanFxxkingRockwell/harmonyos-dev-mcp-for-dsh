"""E2E-oriented tools built on top of core UI/device primitives."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from harmonyos_dev_mcp._common.tools.registry import mcp_tool

from ..container import get_hdc, get_ui_operations
from ..types import ElementWaitState, ListWindowsResult, UITreeResult, WaitForElementResult
from ..ui.common import normalize_bundle_name
from ..ui.normalizers.element import normalize_element
from ..ui.normalizers.window import normalize_windows
from ..ui.tree_parser import UITreeParser
from .device_support import DeviceToolSupport
from harmonyos_dev_mcp._common.tools.response import error_result, from_action_result, mcp_response, ok_result


async def _resolve_target_window(
    *,
    hdc,
    device_id: str,
    bundle_name: Optional[str],
    window_id: Optional[int],
) -> tuple[bool, dict]:
    resolved = await asyncio.to_thread(
        hdc.resolve_window_target,
        device_id,
        bundle_name=bundle_name,
        window_id=window_id,
    )
    if not resolved.get("success", False):
        return False, error_result(
            resolved.get("error_code", "WINDOW_RESOLUTION_ERROR"),
            resolved.get("error", "failed to resolve target window"),
            result={
                "device_id": device_id,
                "window_id": 0,
                "validated_window_id": None,
                "validation_applied": True,
                "capture_scope": "validated_global_dump",
                "ui_tree": {},
                "node_count": 0,
            },
        )
    return True, resolved.get("window") or {"window_id": 0}


def _validate_search_target(
    *,
    text: Optional[str] = None,
    element_type: Optional[str] = None,
    element_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if any([text, element_type, element_id]):
        return None
    return error_result(
        "INVALID_WAIT_TARGET",
        "must provide at least one of text/element_type/element_id",
        result={"element": None, "elapsed_ms": 0},
    )


async def _find_elements_once(
    *,
    ui_ops,
    device_id: str,
    text: Optional[str],
    element_type: Optional[str],
    element_id: Optional[str],
    bundle_name: Optional[str],
    window_id: Optional[int],
):
    return await asyncio.to_thread(
        ui_ops.find_element,
        device_id,
        text=text,
        element_type=element_type,
        element_id=element_id,
        bundle_name=bundle_name,
        window_id=window_id,
    )


async def _find_elements_before_deadline(
    *,
    ui_ops,
    device_id: str,
    text: Optional[str],
    element_type: Optional[str],
    element_id: Optional[str],
    bundle_name: Optional[str],
    window_id: Optional[int],
    deadline: float,
) -> Optional[dict]:
    loop = asyncio.get_running_loop()
    remaining = deadline - loop.time()
    if remaining <= 0:
        return None

    try:
        return await asyncio.wait_for(
            _find_elements_once(
                ui_ops=ui_ops,
                device_id=device_id,
                text=text,
                element_type=element_type,
                element_id=element_id,
                bundle_name=bundle_name,
                window_id=window_id,
            ),
            timeout=remaining,
        )
    except TimeoutError:
        return None


async def _confirm_wait_state(
    *,
    ui_ops,
    device_id: str,
    text: Optional[str],
    element_type: Optional[str],
    element_id: Optional[str],
    bundle_name: Optional[str],
    window_id: Optional[int],
    expected_present: bool,
    interval_ms: int,
    deadline: float,
) -> tuple[Optional[bool], Optional[dict]]:
    if interval_ms <= 0:
        return True, None

    loop = asyncio.get_running_loop()
    remaining = deadline - loop.time()
    if remaining <= 0:
        return None, None

    await asyncio.sleep(min(interval_ms / 1000, remaining))
    confirm_raw = await _find_elements_before_deadline(
        ui_ops=ui_ops,
        device_id=device_id,
        text=text,
        element_type=element_type,
        element_id=element_id,
        bundle_name=bundle_name,
        window_id=window_id,
        deadline=deadline,
    )
    if confirm_raw is None:
        return None, None
    if not confirm_raw.get("success", False):
        return False, confirm_raw

    confirmed_present = bool(confirm_raw.get("elements", []))
    return confirmed_present == expected_present, confirm_raw


@mcp_tool(category="e2e")
@mcp_response("get_ui_tree")
@DeviceToolSupport.handle_tool_error(
    "GET_UI_TREE_ERROR",
    window_id=0,
    validated_window_id=None,
    validation_applied=False,
    capture_scope="global_dump",
    ui_tree={},
    node_count=0,
)
@DeviceToolSupport.with_device(
    window_id=0,
    validated_window_id=None,
    validation_applied=False,
    capture_scope="global_dump",
    ui_tree={},
    node_count=0,
)
async def get_ui_tree(
    device_id: Optional[str] = None,
    bundle_name: Optional[str] = None,
    window_id: Optional[int] = None,
) -> UITreeResult:
    """Capture the UI tree globally or for a validated application window."""
    hdc = get_hdc()
    target_window_id = window_id
    validation_applied = bool(bundle_name or window_id is not None)
    validated_window_id = None

    if validation_applied:
        ok, target_window = await _resolve_target_window(
            hdc=hdc,
            device_id=device_id,
            bundle_name=bundle_name,
            window_id=window_id,
        )
        if not ok:
            return target_window
        target_window_id = target_window.get("window_id", 0)
        validated_window_id = target_window_id

    ui_tree_result = await asyncio.to_thread(hdc.get_ui_tree_raw, device_id, target_window_id)
    ui_tree_check = from_action_result(
        ui_tree_result,
        default_code="UI_TREE_FETCH_ERROR",
        default_detail="failed to fetch ui tree",
        default_result={
            "device_id": device_id,
            "window_id": target_window_id,
            "validated_window_id": validated_window_id,
            "validation_applied": validation_applied,
            "capture_scope": "validated_global_dump" if validation_applied else "global_dump",
            "ui_tree": {},
            "node_count": 0,
        },
    )
    if not ui_tree_check.get("ok", False):
        return ui_tree_check

    raw_tree = ui_tree_result.get("ui_tree")
    if raw_tree is None or not isinstance(raw_tree, (dict, str)):
        return error_result(
            "INVALID_UI_TREE_PAYLOAD",
            "ui tree payload must be a JSON object or string",
            result={
                "device_id": device_id,
                "window_id": target_window_id,
                "validated_window_id": validated_window_id,
                "validation_applied": validation_applied,
                "capture_scope": "validated_global_dump" if validation_applied else "global_dump",
                "ui_tree": {},
                "node_count": 0,
            },
        )
    parser = UITreeParser()
    parsed_tree = parser.parse(json.dumps(raw_tree)) if isinstance(raw_tree, dict) else parser.parse(raw_tree)
    node_count = parsed_tree.get("count", 0) if isinstance(parsed_tree, dict) else 0
    return ok_result(
        {
            "device_id": device_id,
            "window_id": target_window_id,
            "validated_window_id": validated_window_id,
            "validation_applied": validation_applied,
            "capture_scope": "validated_global_dump" if validation_applied else "global_dump",
            "ui_tree": parsed_tree,
            "node_count": node_count,
        }
    )


@mcp_tool(category="e2e")
@mcp_response("list_windows")
@DeviceToolSupport.handle_tool_error("LIST_WINDOWS_ERROR", windows=[], count=0)
@DeviceToolSupport.with_device(windows=[], count=0)
async def list_windows(
    device_id: Optional[str] = None,
    bundle_name: Optional[str] = None,
) -> ListWindowsResult:
    """List current HarmonyOS windows, optionally filtered by bundle name."""
    hdc = get_hdc()
    raw = await asyncio.to_thread(hdc.get_window_list, device_id)
    all_windows = normalize_windows(raw.get("windows", []) if isinstance(raw, dict) else [])
    windows = all_windows

    target_bundle = normalize_bundle_name(bundle_name)
    if target_bundle:
        windows = [window for window in windows if normalize_bundle_name(window.get("bundle_name")) == target_bundle]
    if isinstance(raw, dict):
        raw = dict(raw)
        raw["windows"] = windows
        raw["count"] = len(windows)
        raw["total_count"] = len(all_windows)

    return from_action_result(
        raw,
        default_code="LIST_WINDOWS_ERROR",
        default_detail="failed to list windows",
        default_result={"device_id": device_id, "windows": windows, "count": len(windows), "total_count": len(all_windows)},
    )


@mcp_tool(category="e2e")
@mcp_response("wait_for_element")
@DeviceToolSupport.handle_tool_error("WAIT_ELEMENT_ERROR", state="found", satisfied=False, elapsed_ms=0, element=None)
@DeviceToolSupport.with_device(state="found", satisfied=False, elapsed_ms=0, element=None)
async def wait_for_element(
    device_id: Optional[str] = None,
    bundle_name: Optional[str] = None,
    window_id: Optional[int] = None,
    text: Optional[str] = None,
    element_type: Optional[str] = None,
    element_id: Optional[str] = None,
    state: ElementWaitState = "found",
    timeout_ms: int = 5000,
    interval_ms: int = 300,
) -> WaitForElementResult:
    """Wait until a UI element appears or disappears within a strict wall-clock budget.

    The timeout includes device queries, polling sleeps, and stability confirmation.
    A zero timeout returns immediately without querying the device.
    """
    invalid = _validate_search_target(text=text, element_type=element_type, element_id=element_id)
    if invalid:
        invalid["result"]["state"] = state
        invalid["result"]["satisfied"] = False
        return invalid
    if timeout_ms < 0:
        return error_result(
            "INVALID_TIMEOUT",
            "timeout_ms must be >= 0",
            result={"device_id": device_id, "state": state, "satisfied": False, "elapsed_ms": 0, "element": None},
        )
    if interval_ms < 0:
        return error_result(
            "INVALID_INTERVAL",
            "interval_ms must be >= 0",
            result={"device_id": device_id, "state": state, "satisfied": False, "elapsed_ms": 0, "element": None},
        )
    if state not in ("found", "gone"):
        return error_result(
            "INVALID_WAIT_STATE",
            'state must be "found" or "gone"',
            result={"device_id": device_id, "state": state, "satisfied": False, "elapsed_ms": 0, "element": None},
        )

    ui_ops = get_ui_operations()
    loop = asyncio.get_running_loop()
    started = loop.time()
    deadline = started + max(timeout_ms, 0) / 1000

    def timeout_result(*, raw: Optional[dict] = None, elements: Optional[list] = None):
        elapsed_ms = int((loop.time() - started) * 1000)
        element = None
        if state == "gone" and elements:
            element = normalize_element(
                elements[0],
                bundle_name=bundle_name,
                window_id=(raw or {}).get("window_id", window_id),
            )
        return error_result(
            "WAIT_TIMEOUT",
            f'element did not reach state "{state}" within {timeout_ms}ms',
            result={
                "device_id": device_id,
                "state": state,
                "satisfied": False,
                "elapsed_ms": elapsed_ms,
                "element": element,
            },
        )

    while True:
        raw = await _find_elements_before_deadline(
            ui_ops=ui_ops,
            device_id=device_id,
            text=text,
            element_type=element_type,
            element_id=element_id,
            bundle_name=bundle_name,
            window_id=window_id,
            deadline=deadline,
        )
        if raw is None:
            return timeout_result()

        elapsed_ms = int((loop.time() - started) * 1000)
        if not raw.get("success", False):
            return from_action_result(
                raw,
                default_code="FIND_ELEMENT_ERROR",
                default_detail="find element failed",
                default_result={
                    "device_id": device_id,
                    "state": state,
                    "satisfied": False,
                    "elapsed_ms": elapsed_ms,
                    "element": None,
                },
            )

        elements = raw.get("elements", [])
        expected_present = state == "found"
        if bool(elements) == expected_present:
            confirmed, confirm_raw = await _confirm_wait_state(
                ui_ops=ui_ops,
                device_id=device_id,
                text=text,
                element_type=element_type,
                element_id=element_id,
                bundle_name=bundle_name,
                window_id=window_id,
                expected_present=expected_present,
                interval_ms=interval_ms,
                deadline=deadline,
            )
            if confirmed is None:
                return timeout_result(raw=raw, elements=elements)
            if confirm_raw and not confirm_raw.get("success", False):
                elapsed_ms = int((loop.time() - started) * 1000)
                return from_action_result(
                    confirm_raw,
                    default_code="FIND_ELEMENT_ERROR",
                    default_detail="find element failed",
                    default_result={
                        "device_id": device_id,
                        "state": state,
                        "satisfied": False,
                        "elapsed_ms": elapsed_ms,
                        "element": None,
                    },
                )
            if confirmed:
                final_raw = confirm_raw or raw
                final_elements = final_raw.get("elements", [])
                elapsed_ms = int((loop.time() - started) * 1000)
                return ok_result(
                    {
                        "device_id": device_id,
                        "state": state,
                        "satisfied": True,
                        "elapsed_ms": elapsed_ms,
                        "element": (
                            normalize_element(
                                final_elements[0],
                                bundle_name=bundle_name,
                                window_id=final_raw.get("window_id", window_id),
                            )
                            if expected_present
                            else None
                        ),
                    }
                )
            raw = confirm_raw or raw
            elements = raw.get("elements", [])

        remaining = deadline - loop.time()
        if remaining <= 0:
            return timeout_result(raw=raw, elements=elements)
        await asyncio.sleep(min(interval_ms / 1000, remaining))
