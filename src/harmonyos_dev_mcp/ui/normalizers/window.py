"""Window payload normalization helpers."""

from __future__ import annotations

from typing import Any, Dict

from ..common import normalize_bundle_name, rect_to_bounds


def normalize_window(window: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(window)
    bundle_name = normalized.get("bundle_name")
    normalized["bundle_name"] = bundle_name if isinstance(bundle_name, str) else ""
    normalized["bundle_name_resolved"] = bool(normalize_bundle_name(normalized.get("bundle_name")))
    normalized.setdefault("is_visible", False)
    normalized["bounds"] = rect_to_bounds(normalized.get("rect"))
    return normalized


def normalize_windows(windows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    normalized = [normalize_window(window) for window in windows]
    foreground_by_display: dict[int, int] = {}

    for index, window in enumerate(normalized):
        if not window.get("is_visible") or window.get("type") != 1:
            continue
        display_id = int(window.get("display_id", 0))
        zord = int(window.get("zord", -1))
        current_index = foreground_by_display.get(display_id)
        if current_index is None or zord > int(normalized[current_index].get("zord", -1)):
            foreground_by_display[display_id] = index

    for index, window in enumerate(normalized):
        display_id = int(window.get("display_id", 0))
        window["is_foreground"] = foreground_by_display.get(display_id) == index

    return normalized
