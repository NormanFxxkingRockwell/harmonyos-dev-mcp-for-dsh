"""UI automation tools."""

import asyncio
import os
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from harmonyos_dev_mcp._common.tools.registry import mcp_tool

from ..container import get_hdc, get_ui_operations
from ..types import (
    ClickResult,
    DragResult,
    FindElementsResult,
    InputTextResult,
    LongPressResult,
    PressKeyResult,
    ScreenshotResult,
    SwipeResult,
)
from ..ui.keycodes import KeyCode, ResolvedKey, resolve_key
from ..ui.normalizers.element import attach_element_metadata, build_lookup_hint, compact_candidate_handles
from .device_support import DeviceToolSupport
from harmonyos_dev_mcp._common.tools.response import error_result, from_action_result, mcp_response

_MODIFIER_KEYS = {
    "alt": ("Alt", int(KeyCode.ALT_LEFT)),
    "ctrl": ("Ctrl", int(KeyCode.CTRL_LEFT)),
    "control": ("Ctrl", int(KeyCode.CTRL_LEFT)),
    "meta": ("Meta", int(KeyCode.META_LEFT)),
    "shift": ("Shift", int(KeyCode.SHIFT_LEFT)),
}


def _with_success_message(raw: Any, message: str) -> Any:
    if not isinstance(raw, dict):
        return raw
    normalized = dict(raw)
    normalized.pop("action", None)
    if normalized.get("success", False):
        normalized["message"] = message
    return normalized


def _is_close(a: Any, b: Any, tolerance: int = 12) -> bool:
    if a is None or b is None:
        return False
    return abs(int(a) - int(b)) <= tolerance


def _resolve_modifier(modifier: str) -> Optional[Tuple[str, int]]:
    alias = str(modifier).strip().replace("-", "_").replace(" ", "_").lower()
    return _MODIFIER_KEYS.get(alias)


def _press_key_result(
    resolved_key: Optional[ResolvedKey],
    *,
    modifiers: Optional[List[str]] = None,
    event_key_codes: Optional[List[int]] = None,
) -> Dict[str, Any]:
    return {
        "key": resolved_key.name if resolved_key is not None else None,
        "key_code": resolved_key.code if resolved_key is not None else None,
        "modifiers": list(modifiers or []),
        "event_key_codes": list(event_key_codes or []),
    }


def _match_handle_candidates(candidates: list[Dict[str, Any]], handle: Dict[str, Any]) -> list[Dict[str, Any]]:
    exact = []
    approximate = []
    for candidate in candidates:
        candidate_window = candidate.get("window_id")
        handle_window = handle.get("window_id")
        if candidate_window is not None and handle_window is not None and candidate_window != handle_window:
            continue

        if handle.get("compid") and candidate.get("compid") == handle.get("compid"):
            exact.append(candidate)
            continue

        if handle.get("id") and candidate.get("id") == handle.get("id"):
            if not handle.get("type") or candidate.get("type") == handle.get("type"):
                exact.append(candidate)
                continue

        if (
            handle.get("type")
            and candidate.get("type") == handle.get("type")
            and _is_close(candidate.get("x"), handle.get("x"))
            and _is_close(candidate.get("y"), handle.get("y"))
        ):
            approximate.append(candidate)

    return exact or approximate


def _resolved_result(
    element: Dict[str, Any],
    *,
    resolved_via: str,
    handle_refreshed: bool,
) -> Dict[str, Any]:
    return {
        "x": int(element["x"]),
        "y": int(element["y"]),
        "element_handle": dict(element.get("element_handle") or {}),
        "resolved_via": resolved_via,
        "handle_refreshed": handle_refreshed,
    }


async def _perform_resolved_action(
    *,
    action_fn,
    device_id: str,
    resolved: Dict[str, Any],
    success_message: str,
    default_code: str,
    default_detail: str,
    extra_args: tuple = (),
    extra_result: Optional[Dict[str, Any]] = None,
) -> dict:
    raw = await asyncio.to_thread(action_fn, device_id, resolved["x"], resolved["y"], *extra_args)
    raw = _with_success_message(raw, success_message)
    default_result = dict(resolved)
    if extra_result:
        default_result.update(extra_result)
    return from_action_result(
        raw,
        default_code=default_code,
        default_detail=default_detail,
        default_result=default_result,
    )


async def _resolve_handle_coords(
    device_id: str,
    element_handle: Any,
) -> Tuple[bool, Union[Dict[str, Any], dict]]:
    if not isinstance(element_handle, dict):
        return False, error_result(
            "INVALID_ELEMENT_HANDLE",
            "element_handle must be an object taken directly from find_elements/wait_for_element. Do not pass a JSON string.",
            result={"elements": [], "count": 0},
        )

    ui_ops = get_ui_operations()
    lookup_hint = element_handle.get("lookup_hint") if isinstance(element_handle.get("lookup_hint"), dict) else {}
    bundle_name = element_handle.get("bundle_name") or lookup_hint.get("bundle_name")
    window_id = element_handle.get("window_id", lookup_hint.get("window_id"))

    raw = await asyncio.to_thread(
        ui_ops.find_element,
        device_id,
        element_id=element_handle.get("id"),
        element_type=element_handle.get("type"),
        bundle_name=bundle_name,
        window_id=window_id,
    )
    if not raw.get("success", False):
        return False, from_action_result(
            raw,
            default_code="FIND_ELEMENT_ERROR",
            default_detail="find element failed",
            default_result={"elements": [], "count": 0},
        )

    candidates = attach_element_metadata(
        raw.get("elements", []),
        bundle_name=bundle_name,
        window_id=raw.get("window_id", window_id),
        lookup_hint=lookup_hint,
    )
    matches = _match_handle_candidates(candidates, element_handle)
    if len(matches) == 1 and matches[0].get("x") is not None and matches[0].get("y") is not None:
        return True, _resolved_result(matches[0], resolved_via="handle", handle_refreshed=False)

    if not lookup_hint:
        return False, error_result(
            "ELEMENT_NOT_FOUND",
            "element_handle is stale and no lookup_hint is available for retry",
            result={"elements": [], "count": 0},
        )

    retry_raw = await asyncio.to_thread(
        ui_ops.find_element,
        device_id,
        text=lookup_hint.get("text"),
        element_type=lookup_hint.get("element_type"),
        element_id=lookup_hint.get("element_id"),
        bundle_name=lookup_hint.get("bundle_name"),
        window_id=lookup_hint.get("window_id"),
    )
    if not retry_raw.get("success", False):
        return False, from_action_result(
            retry_raw,
            default_code="FIND_ELEMENT_ERROR",
            default_detail="find element failed",
            default_result={"elements": [], "count": 0},
        )

    retry_candidates = attach_element_metadata(
        retry_raw.get("elements", []),
        bundle_name=lookup_hint.get("bundle_name"),
        window_id=retry_raw.get("window_id", lookup_hint.get("window_id")),
        lookup_hint=lookup_hint,
    )
    if len(retry_candidates) == 1 and retry_candidates[0].get("x") is not None and retry_candidates[0].get("y") is not None:
        return True, _resolved_result(retry_candidates[0], resolved_via="lookup_hint", handle_refreshed=True)

    if len(retry_candidates) > 1:
        return False, error_result(
            "AMBIGUOUS_ELEMENT_MATCH",
            "element_handle is stale and lookup_hint matched multiple elements; use a more specific text, element_id, or coordinates",
            result={
                "elements": retry_candidates,
                "count": len(retry_candidates),
                "match_count": len(retry_candidates),
                "candidate_handles": compact_candidate_handles(retry_candidates),
            },
        )

    return False, error_result(
        "ELEMENT_NOT_FOUND",
        "element_handle is stale and lookup_hint retry did not find the target element",
        result={"elements": [], "count": 0},
    )


async def _resolve_element_coords(
    device_id: str,
    text: Optional[str] = None,
    element_type: Optional[str] = None,
    element_id: Optional[str] = None,
    bundle_name: Optional[str] = None,
    window_id: Optional[int] = None,
) -> Tuple[bool, Union[Tuple[int, int], dict]]:
    ui_ops = get_ui_operations()
    raw = await asyncio.to_thread(
        ui_ops.find_element,
        device_id,
        text=text,
        element_type=element_type,
        element_id=element_id,
        bundle_name=bundle_name,
        window_id=window_id,
    )
    if not raw.get("success", False):
        return False, from_action_result(
            raw,
            default_code="FIND_ELEMENT_ERROR",
            default_detail="find element failed",
            default_result={"elements": [], "count": 0},
        )

    elements = raw.get("elements", [])
    if not elements:
        return False, error_result(
            "ELEMENT_NOT_FOUND",
            f"element not found: text={text}, type={element_type}, id={element_id}",
            result={"elements": [], "count": 0},
        )

    element = elements[0]
    if "x" not in element or "y" not in element:
        return False, error_result(
            "INVALID_ELEMENT_COORDS",
            f"invalid element coords: {element}",
            result={"elements": elements, "count": len(elements)},
        )
    return True, (element["x"], element["y"])


async def _verify_input_handle(
    *,
    device_id: str,
    element_handle: Dict[str, Any],
    expected_text: str,
    mode: Literal["replace", "append"],
    action_result: dict,
) -> dict:
    """Re-read a handled input after writing so command success cannot mask a UI miss."""
    verified_ok, verified = await _resolve_handle_coords(device_id, element_handle)
    result_data = dict(action_result.get("result") or {})
    if not verified_ok:
        result_data["verified"] = False
        return error_result(
            "TEXT_VERIFICATION_FAILED",
            "input command succeeded, but the target element could not be re-read",
            result=result_data,
        )

    verified_handle = dict(verified.get("element_handle") or {})
    actual_text = verified_handle.get("text")
    matched = (
        actual_text == expected_text
        if mode == "replace"
        else isinstance(actual_text, str) and actual_text.endswith(expected_text)
    )
    result_data.update(
        {
            "actual_text": actual_text,
            "verified": matched,
            "element_handle": verified_handle,
        }
    )
    if not matched:
        return error_result(
            "TEXT_VERIFICATION_FAILED",
            (
                f"input command succeeded, but UI text verification failed: "
                f"expected {'exact text' if mode == 'replace' else 'suffix'} "
                f"{expected_text!r}, got {actual_text!r}"
            ),
            result=result_data,
        )

    action_result["result"] = result_data
    return action_result


@mcp_tool(category="ui")
@mcp_response("click")
@DeviceToolSupport.handle_tool_error("CLICK_ERROR", x=0, y=0)
@DeviceToolSupport.with_device(x=0, y=0)
async def click(
    device_id: Optional[str] = None,
    x: Optional[int] = None,
    y: Optional[int] = None,
    element_handle: Optional[Dict[str, Any]] = None,
    text: Optional[str] = None,
    element_type: Optional[str] = None,
    element_id: Optional[str] = None,
    count: Literal[1, 2] = 1,
    bundle_name: Optional[str] = None,
) -> ClickResult:
    """Click a UI target once or twice by coordinates, handle, or search criteria."""
    has_coords = x is not None and y is not None
    has_handle = element_handle is not None
    has_search = bool(text or element_type or element_id)

    if count not in {1, 2}:
        return error_result(
            "INVALID_CLICK_COUNT",
            "count must be 1 or 2",
            result={"x": x or 0, "y": y or 0, "count": count},
        )

    if has_coords and (has_handle or has_search):
        return error_result(
            "PARAM_CONFLICT",
            "cannot provide coordinates together with element_handle or search criteria",
            result={"x": x, "y": y},
        )

    ui_ops = get_ui_operations()
    click_fn = ui_ops.double_click if count == 2 else ui_ops.click
    success_message = "double click succeeded" if count == 2 else "click succeeded"

    if has_coords:
        return await _perform_resolved_action(
            action_fn=click_fn,
            device_id=device_id,
            resolved={
                "x": x,
                "y": y,
                "resolved_via": "coordinates",
                "handle_refreshed": False,
                "element_handle": None,
            },
            success_message=success_message,
            default_code="CLICK_ERROR",
            default_detail="click failed",
            extra_result={"count": count},
        )

    if has_handle:
        ok, resolved = await _resolve_handle_coords(device_id, element_handle)
        if not ok:
            return resolved
        return await _perform_resolved_action(
            action_fn=click_fn,
            device_id=device_id,
            resolved=resolved,
            success_message=success_message,
            default_code="CLICK_ERROR",
            default_detail="click failed",
            extra_result={"count": count},
        )

    if has_search:
        ok, coords = await _resolve_element_coords(
            device_id,
            text=text,
            element_type=element_type,
            element_id=element_id,
            bundle_name=bundle_name,
        )
        if not ok:
            return coords
        ex, ey = coords
        return await _perform_resolved_action(
            action_fn=click_fn,
            device_id=device_id,
            resolved={
                "x": ex,
                "y": ey,
                "resolved_via": "search",
                "handle_refreshed": False,
                "element_handle": None,
            },
            success_message=success_message,
            default_code="CLICK_ERROR",
            default_detail="click failed",
            extra_result={"count": count},
        )

    return error_result(
        "MISSING_PARAMS",
        "must provide (x,y), element_handle, or (text/element_type)",
        result={"x": x or 0, "y": y or 0},
    )


@mcp_tool(category="ui")
@mcp_response("long_press")
@DeviceToolSupport.handle_tool_error("LONG_PRESS_ERROR")
@DeviceToolSupport.with_device()
async def long_press(
    device_id: Optional[str] = None,
    x: Optional[int] = None,
    y: Optional[int] = None,
    element_handle: Optional[Dict[str, Any]] = None,
    text: Optional[str] = None,
    element_type: Optional[str] = None,
    element_id: Optional[str] = None,
    bundle_name: Optional[str] = None,
) -> LongPressResult:
    """Long-press a UI target by coordinates, handle, or search criteria."""
    ui_ops = get_ui_operations()

    if x is not None and y is not None and (element_handle is not None or text or element_type or element_id):
        return error_result(
            "PARAM_CONFLICT",
            "cannot provide coordinates together with element_handle or search criteria",
            result={"x": x, "y": y},
        )

    if x is not None and y is not None:
        return await _perform_resolved_action(
            action_fn=ui_ops.long_click,
            device_id=device_id,
            resolved={
                "x": x,
                "y": y,
                "resolved_via": "coordinates",
                "handle_refreshed": False,
                "element_handle": None,
            },
            success_message="long press succeeded",
            default_code="LONG_PRESS_ERROR",
            default_detail="long press failed",
        )

    if element_handle is not None:
        ok, resolved = await _resolve_handle_coords(device_id, element_handle)
        if not ok:
            return resolved
        return await _perform_resolved_action(
            action_fn=ui_ops.long_click,
            device_id=device_id,
            resolved=resolved,
            success_message="long press succeeded",
            default_code="LONG_PRESS_ERROR",
            default_detail="long press failed",
        )

    if text or element_type or element_id:
        ok, coords = await _resolve_element_coords(
            device_id,
            text=text,
            element_type=element_type,
            element_id=element_id,
            bundle_name=bundle_name,
        )
        if not ok:
            return coords
        ex, ey = coords
        return await _perform_resolved_action(
            action_fn=ui_ops.long_click,
            device_id=device_id,
            resolved={
                "x": ex,
                "y": ey,
                "resolved_via": "search",
                "handle_refreshed": False,
                "element_handle": None,
            },
            success_message="long press succeeded",
            default_code="LONG_PRESS_ERROR",
            default_detail="long press failed",
        )

    return error_result(
        "MISSING_PARAMS",
        "must provide coordinates, element_handle, or search criteria",
        result={"x": 0, "y": 0},
    )


@mcp_tool(category="ui")
@mcp_response("swipe")
@DeviceToolSupport.handle_tool_error("SWIPE_ERROR", from_x=0, from_y=0, to_x=0, to_y=0, direction=None)
@DeviceToolSupport.with_device(from_x=0, from_y=0, to_x=0, to_y=0, direction=None)
async def swipe(
    device_id: Optional[str] = None,
    from_x: Optional[int] = None,
    from_y: Optional[int] = None,
    to_x: Optional[int] = None,
    to_y: Optional[int] = None,
    direction: Optional[str] = None,
    speed: int = 600,
) -> SwipeResult:
    """Swipe by direction or explicit start and end coordinates."""
    default_result = {
        "from_x": from_x or 0,
        "from_y": from_y or 0,
        "to_x": to_x or 0,
        "to_y": to_y or 0,
        "direction": direction,
    }

    ui_ops = get_ui_operations()

    if direction and any(v is not None for v in [from_x, from_y, to_x, to_y]):
        return error_result(
            "PARAM_CONFLICT",
            "cannot provide direction together with explicit swipe coordinates",
            result=default_result,
        )

    if direction:
        raw = await asyncio.to_thread(ui_ops.swipe_direction, device_id, direction, speed)
        raw = _with_success_message(raw, "swipe succeeded")
        return from_action_result(
            raw,
            default_code="SWIPE_ERROR",
            default_detail="swipe failed",
            default_result=default_result,
        )

    if all(v is not None for v in [from_x, from_y, to_x, to_y]):
        raw = await asyncio.to_thread(ui_ops.swipe, device_id, from_x, from_y, to_x, to_y, speed)
        raw = _with_success_message(raw, "swipe succeeded")
        return from_action_result(
            raw,
            default_code="SWIPE_ERROR",
            default_detail="swipe failed",
            default_result=default_result,
        )

    return error_result("MISSING_PARAMS", "must provide swipe coords or direction", result=default_result)


@mcp_tool(category="ui")
@mcp_response("input_text")
@DeviceToolSupport.handle_tool_error("INPUT_TEXT_ERROR", text="", x=0, y=0)
@DeviceToolSupport.with_device(text="", x=0, y=0)
async def input_text(
    text: str,
    device_id: Optional[str] = None,
    x: Optional[int] = None,
    y: Optional[int] = None,
    element_handle: Optional[Dict[str, Any]] = None,
    element_text: Optional[str] = None,
    element_type: Optional[str] = None,
    element_id: Optional[str] = None,
    bundle_name: Optional[str] = None,
    mode: Literal["replace", "append"] = "replace",
) -> InputTextResult:
    """
    Set an input field to UTF-8 text, or append at the end when mode is ``append``.

    For reliable automation, first call find_elements/wait_for_element and pass its
    element_handle; handle mode re-reads the field and verifies the final text.
    Coordinates and search criteria remain best-effort and return verified=false.
    Replace mode is the default, and an empty replacement clears the field.
    """

    default_result = {"text": text or "", "x": x or 0, "y": y or 0, "mode": mode}

    if text is None:
        return error_result("MISSING_TEXT", "text is required", result=default_result)
    if mode not in {"append", "replace"}:
        return error_result(
            "INVALID_MODE",
            "mode must be 'append' or 'replace'",
            result=default_result,
        )
    if mode == "append" and text == "":
        return error_result(
            "MISSING_TEXT",
            "text must not be empty in append mode; use replace mode to clear a field",
            result=default_result,
        )

    ui_ops = get_ui_operations()
    action_fn = ui_ops.input_text if mode == "append" else ui_ops.replace_text

    if x is not None and y is not None and (element_handle is not None or element_text or element_type or element_id):
        return error_result(
            "PARAM_CONFLICT",
            "cannot provide coordinates together with element_handle or search criteria",
            result=default_result,
        )

    if x is not None and y is not None:
        return await _perform_resolved_action(
            action_fn=action_fn,
            device_id=device_id,
            resolved={
                "text": text,
                "x": x,
                "y": y,
                "resolved_via": "coordinates",
                "handle_refreshed": False,
                "element_handle": None,
                "mode": mode,
            },
            success_message="input text succeeded",
            default_code="INPUT_TEXT_ERROR",
            default_detail="input text failed",
            extra_args=(text,),
            extra_result={"mode": mode, "verified": False},
        )

    if element_handle is not None:
        ok, resolved = await _resolve_handle_coords(device_id, element_handle)
        if not ok:
            return resolved
        action_result = await _perform_resolved_action(
            action_fn=action_fn,
            device_id=device_id,
            resolved=resolved,
            success_message="input text succeeded",
            default_code="INPUT_TEXT_ERROR",
            default_detail="input text failed",
            extra_args=(text,),
            extra_result={"text": text, "mode": mode, "verified": False},
        )
        if not action_result.get("ok", False):
            return action_result
        return await _verify_input_handle(
            device_id=device_id,
            element_handle=resolved["element_handle"],
            expected_text=text,
            mode=mode,
            action_result=action_result,
        )

    if element_text or element_type or element_id:
        ok, coords = await _resolve_element_coords(
            device_id,
            text=element_text,
            element_type=element_type,
            element_id=element_id,
            bundle_name=bundle_name,
        )
        if not ok:
            if isinstance(coords, dict) and coords.get("error", {}).get("code") == "ELEMENT_NOT_FOUND":
                coords["error"]["detail"] = (
                    "element not found for input_text lookup; call find_elements with "
                    "more specific criteria and pass its element_handle"
                )
            return coords
        ex, ey = coords
        return await _perform_resolved_action(
            action_fn=action_fn,
            device_id=device_id,
            resolved={
                "text": text,
                "x": ex,
                "y": ey,
                "resolved_via": "search",
                "handle_refreshed": False,
                "element_handle": None,
                "mode": mode,
            },
            success_message="input text succeeded",
            default_code="INPUT_TEXT_ERROR",
            default_detail="input text failed",
            extra_args=(text,),
            extra_result={"mode": mode, "verified": False},
        )

    return error_result(
        "MISSING_PARAMS",
        "must provide coordinates, element_handle, or search criteria",
        result=default_result,
    )


@mcp_tool(category="ui")
@mcp_response("press_key")
@DeviceToolSupport.handle_tool_error(
    "PRESS_KEY_ERROR",
    key=None,
    key_code=None,
    modifiers=[],
    event_key_codes=[],
)
@DeviceToolSupport.with_device(
    key=None,
    key_code=None,
    modifiers=[],
    event_key_codes=[],
)
async def press_key(
    key: Union[str, int],
    modifiers: Optional[List[Literal["Ctrl", "Alt", "Shift", "Meta"]]] = None,
    device_id: Optional[str] = None,
) -> PressKeyResult:
    """
    Press one logical key, optionally with Ctrl, Alt, Shift, or Meta modifiers.

    Use ``input_text`` to enter strings. Use this tool for system keys and
    shortcuts such as key="Home" or key="V", modifiers=["Ctrl"]. ``key`` accepts
    every official HarmonyOS ``KEYCODE_*`` name and numeric value. Names are
    case- and separator-insensitive: ``Tab``, ``KEYCODE_TAB``, ``page-up``, and
    ``page_up`` are valid. Use ``Backspace`` for KEYCODE_DEL and ``Delete`` for
    KEYCODE_FORWARD_DEL. The result returns the canonical key name, its numeric
    code, and the exact key codes sent in the single HarmonyOS keyEvent.
    """

    resolved_key = resolve_key(key)
    if resolved_key is None:
        return error_result(
            "INVALID_KEY",
            (
                f"unsupported key: {key}. Use any official HarmonyOS KEYCODE_* "
                "name (case and separators are optional) or its numeric value"
            ),
            result=_press_key_result(None),
        )

    requested_modifiers = list(modifiers or [])
    if len(requested_modifiers) > 2:
        return error_result(
            "INVALID_MODIFIER_COUNT",
            "HarmonyOS keyEvent supports at most two modifiers with one primary key",
            result=_press_key_result(resolved_key, modifiers=requested_modifiers),
        )

    normalized_modifiers: List[str] = []
    modifier_codes: List[int] = []
    for requested_modifier in requested_modifiers:
        resolved_modifier = _resolve_modifier(requested_modifier)
        if resolved_modifier is None:
            return error_result(
                "INVALID_MODIFIER",
                f"unsupported modifier: {requested_modifier}. Use Ctrl, Alt, Shift, or Meta",
                result=_press_key_result(resolved_key, modifiers=requested_modifiers),
            )
        modifier_name, modifier_code = resolved_modifier
        if modifier_name in normalized_modifiers:
            return error_result(
                "DUPLICATE_MODIFIER",
                f"modifier {modifier_name} was provided more than once",
                result=_press_key_result(resolved_key, modifiers=requested_modifiers),
            )
        normalized_modifiers.append(modifier_name)
        modifier_codes.append(modifier_code)

    if resolved_key.code in modifier_codes:
        return error_result(
            "DUPLICATE_MODIFIER",
            "the primary key duplicates one of the modifiers",
            result=_press_key_result(resolved_key, modifiers=normalized_modifiers),
        )

    event_key_codes = [*modifier_codes, resolved_key.code]
    ui_ops = get_ui_operations()
    if modifier_codes:
        raw = await asyncio.to_thread(ui_ops.send_key_event, device_id, event_key_codes)
    else:
        raw = await asyncio.to_thread(ui_ops.press_key, device_id, resolved_key.code)
    if isinstance(raw, dict):
        raw = dict(raw)
        raw.pop("key", None)
        raw.pop("keys", None)
        raw.pop("action", None)
        raw.update(
            _press_key_result(
                resolved_key,
                modifiers=normalized_modifiers,
                event_key_codes=event_key_codes,
            )
        )
    raw = _with_success_message(raw, "key press succeeded")
    return from_action_result(
        raw,
        default_code="PRESS_KEY_ERROR",
        default_detail="key press failed",
        default_result=_press_key_result(
            resolved_key,
            modifiers=normalized_modifiers,
            event_key_codes=event_key_codes,
        ),
    )


@mcp_tool(category="ui")
@mcp_response("find_elements")
@DeviceToolSupport.handle_tool_error("FIND_ELEMENT_ERROR", elements=[], count=0)
@DeviceToolSupport.with_device(elements=[], count=0)
async def find_elements(
    device_id: Optional[str] = None,
    text: Optional[str] = None,
    element_type: Optional[str] = None,
    element_id: Optional[str] = None,
    bundle_name: Optional[str] = None,
    window_id: Optional[int] = None,
) -> FindElementsResult:
    """Find UI elements and return reusable element handles."""
    if not any([text, element_type, element_id]):
        return error_result(
            "MISSING_SEARCH_CRITERIA",
            "must provide at least one of text/element_type/element_id",
            result={"elements": [], "count": 0},
        )

    ui_ops = get_ui_operations()
    raw = await asyncio.to_thread(
        ui_ops.find_element,
        device_id,
        text=text,
        element_type=element_type,
        element_id=element_id,
        bundle_name=bundle_name,
        window_id=window_id,
    )
    lookup_hint = build_lookup_hint(
        text=text,
        element_type=element_type,
        element_id=element_id,
        bundle_name=bundle_name,
        window_id=raw.get("window_id", window_id),
    )
    elements = attach_element_metadata(
        raw.get("elements", []),
        bundle_name=bundle_name,
        window_id=raw.get("window_id", window_id),
        lookup_hint=lookup_hint,
    )
    base = {"elements": elements, "count": raw.get("count", len(elements))}
    if raw.get("success", False) and base["count"] == 0:
        return error_result(
            "ELEMENT_NOT_FOUND",
            f"element not found: text={text}, type={element_type}, id={element_id}",
            result=base,
        )
    if isinstance(raw, dict):
        raw = dict(raw)
        raw["elements"] = elements
        raw["count"] = base["count"]
    return from_action_result(
        raw,
        default_code="FIND_ELEMENT_ERROR",
        default_detail="find element failed",
        default_result=base,
    )


@mcp_tool(category="ui")
@mcp_response("screenshot")
@DeviceToolSupport.handle_tool_error("SCREENSHOT_ERROR")
@DeviceToolSupport.with_device()
@DeviceToolSupport.validate_params(local_path=["path"])
async def screenshot(
    device_id: Optional[str] = None,
    local_path: Optional[str] = None,
    display_id: int = 0,
    left: Optional[int] = None,
    top: Optional[int] = None,
    right: Optional[int] = None,
    bottom: Optional[int] = None,
) -> ScreenshotResult:
    """Capture the full display or a rectangular screen region."""
    hdc = get_hdc()

    has_partial_bounds = any(v is not None for v in [left, top, right, bottom]) and not all(
        v is not None for v in [left, top, right, bottom]
    )
    if has_partial_bounds:
        return error_result(
            "PARAM_CONFLICT",
            "left, top, right, and bottom must all be provided together for region screenshots",
            result={"bounds": {"left": left, "top": top, "right": right, "bottom": bottom}},
        )

    if not local_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshots_dir = os.path.join(os.path.expanduser("~"), "harmonyos-screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)
        suffix = "element" if left is not None else "screenshot"
        local_path = os.path.join(screenshots_dir, f"{suffix}_{timestamp}.jpeg")

    if left is not None and top is not None and right is not None and bottom is not None:
        bounds = {"left": left, "top": top, "right": right, "bottom": bottom}
        raw = await asyncio.to_thread(hdc.take_element_screenshot, device_id, local_path, bounds)
        raw = _with_success_message(raw, "element screenshot succeeded")
        return from_action_result(
            raw,
            default_code="SCREENSHOT_ERROR",
            default_detail="element screenshot failed",
            default_result={"bounds": bounds},
        )

    raw = await asyncio.to_thread(hdc.take_screenshot, device_id, local_path, display_id)
    raw = _with_success_message(raw, "screenshot succeeded")
    return from_action_result(
        raw,
        default_code="SCREENSHOT_ERROR",
        default_detail="screenshot failed",
    )


@mcp_tool(category="ui")
@mcp_response("drag")
@DeviceToolSupport.handle_tool_error("DRAG_ERROR")
@DeviceToolSupport.with_device()
async def drag(
    device_id: Optional[str] = None,
    from_x: Optional[int] = None,
    from_y: Optional[int] = None,
    to_x: Optional[int] = None,
    to_y: Optional[int] = None,
    speed: int = 600,
) -> DragResult:
    """Drag from one screen coordinate to another."""
    if not all(v is not None for v in [from_x, from_y, to_x, to_y]):
        return error_result(
            "MISSING_PARAMS",
            "must provide from_x, from_y, to_x, to_y",
            result={"from_x": from_x or 0, "from_y": from_y or 0, "to_x": to_x or 0, "to_y": to_y or 0},
        )

    ui_ops = get_ui_operations()
    raw = await asyncio.to_thread(ui_ops.drag, device_id, from_x, from_y, to_x, to_y, speed)
    raw = _with_success_message(raw, "drag succeeded")
    if isinstance(raw, dict):
        raw.pop("from", None)
        raw.pop("to", None)
    return from_action_result(
        raw,
        default_code="DRAG_ERROR",
        default_detail="drag failed",
        default_result={"from_x": from_x, "from_y": from_y, "to_x": to_x, "to_y": to_y},
    )
