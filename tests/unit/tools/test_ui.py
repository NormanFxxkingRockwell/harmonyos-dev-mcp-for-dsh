"""UI tool tests with standardized MCP response envelope."""

from copy import deepcopy
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.asyncio


def _sample_handle(*, with_lookup_hint: bool = True) -> dict:
    handle = {
        "window_id": 1,
        "id": "btn_login",
        "compid": "comp_btn_login",
        "type": "Button",
        "text": "Button",
        "x": 100,
        "y": 200,
        "bounds": {"left": 80, "top": 180, "right": 120, "bottom": 220},
        "bundle_name": "com.example.app",
    }
    if with_lookup_hint:
        handle["lookup_hint"] = {"text": "Button", "element_type": "Button", "bundle_name": "com.example.app", "window_id": 1}
    return handle


class TestClick:
    async def test_click_by_coordinates(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.click(x=100, y=200))

        assert sc["ok"] is True
        assert sc["result"]["message"] == "click succeeded"
        assert sc["result"]["x"] == 100
        assert sc["result"]["y"] == 200
        assert sc["result"]["count"] == 1
        assert sc["result"]["resolved_via"] == "coordinates"
        assert "action" not in sc["result"]

    async def test_click_by_text(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.click(text="登录"))

        assert sc["ok"] is True
        assert sc["result"]["resolved_via"] == "search"
        mock_ui_operations.find_element.assert_called_once()
        mock_ui_operations.click.assert_called_once()

    async def test_click_by_element_id(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.click(element_id="btn_login"))

        assert sc["ok"] is True
        assert sc["result"]["resolved_via"] == "search"
        mock_ui_operations.find_element.assert_called_once()

    async def test_click_by_handle(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.click(element_handle=_sample_handle()))

        assert sc["ok"] is True
        assert sc["result"]["resolved_via"] == "handle"
        assert sc["result"]["handle_refreshed"] is False
        assert sc["result"]["element_handle"]["compid"] == "comp_btn_login"
        mock_ui_operations.click.assert_called_once_with("device_001", 100, 200)

    async def test_click_stale_handle_retries_once(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        mock_ui_operations.find_element.side_effect = [
            {"success": True, "window_id": 1, "elements": [], "count": 0},
            {
                "success": True,
                "window_id": 1,
                "elements": [
                    {
                        "id": "btn_login_new",
                        "compid": "comp_btn_login_new",
                        "x": 140,
                        "y": 240,
                        "left": 120,
                        "top": 220,
                        "width": 40,
                        "height": 40,
                        "text": "Button",
                        "type": "Button",
                    }
                ],
                "count": 1,
            },
        ]

        sc = unwrap_result(await ui.click(element_handle=_sample_handle()))

        assert sc["ok"] is True
        assert sc["result"]["resolved_via"] == "lookup_hint"
        assert sc["result"]["handle_refreshed"] is True
        assert sc["result"]["element_handle"]["compid"] == "comp_btn_login_new"
        mock_ui_operations.click.assert_called_once_with("device_001", 140, 240)

    async def test_click_stale_handle_without_lookup_hint_fails(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result
    ):
        from harmonyos_dev_mcp.tools import ui

        mock_ui_operations.find_element.return_value = {"success": True, "window_id": 1, "elements": [], "count": 0}

        sc = unwrap_result(await ui.click(element_handle=_sample_handle(with_lookup_hint=False)))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "ELEMENT_NOT_FOUND"

    async def test_click_stale_handle_with_ambiguous_retry_fails(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result
    ):
        from harmonyos_dev_mcp.tools import ui

        mock_ui_operations.find_element.side_effect = [
            {"success": True, "window_id": 1, "elements": [], "count": 0},
            {
                "success": True,
                "window_id": 1,
                "elements": [
                    {"id": "a", "compid": "a", "x": 100, "y": 200, "text": "Button", "type": "Button"},
                    {"id": "b", "compid": "b", "x": 120, "y": 220, "text": "Button", "type": "Button"},
                ],
                "count": 2,
            },
        ]

        sc = unwrap_result(await ui.click(element_handle=_sample_handle()))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "AMBIGUOUS_ELEMENT_MATCH"
        assert "more specific text" in sc["error"]["detail"]
        assert sc["result"]["match_count"] == 2
        assert len(sc["result"]["candidate_handles"]) == 2
        assert sc["result"]["candidate_handles"][0]["compid"] == "a"

    async def test_double_click(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.click(x=100, y=200, count=2))

        assert sc["ok"] is True
        assert sc["result"]["message"] == "double click succeeded"
        assert sc["result"]["count"] == 2
        mock_ui_operations.double_click.assert_called_once_with("device_001", 100, 200)

    async def test_click_not_found(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        mock_ui_operations.find_element.return_value = {"success": True, "elements": [], "count": 0}

        sc = unwrap_result(await ui.click(text="missing"))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "ELEMENT_NOT_FOUND"

    async def test_click_requires_params(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.click())

        assert sc["ok"] is False
        assert sc["error"]["code"] == "MISSING_PARAMS"

    async def test_click_rejects_coordinate_conflict(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result
    ):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.click(x=100, y=200, element_handle=_sample_handle()))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "PARAM_CONFLICT"

    async def test_click_rejects_invalid_count(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result
    ):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.click(x=100, y=200, count=3))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "INVALID_CLICK_COUNT"


class TestSwipe:
    async def test_swipe_by_coordinates(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.swipe(from_x=100, from_y=500, to_x=100, to_y=200))

        assert sc["ok"] is True
        assert sc["result"]["message"] == "swipe succeeded"
        mock_ui_operations.swipe.assert_called_once()

    async def test_swipe_by_direction(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.swipe(direction="up"))

        assert sc["ok"] is True
        assert sc["result"]["message"] == "swipe succeeded"
        mock_ui_operations.swipe_direction.assert_called_once_with("device_001", "up", 600)

    async def test_swipe_with_custom_speed(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.swipe(direction="down", speed=1000))

        assert sc["ok"] is True
        mock_ui_operations.swipe_direction.assert_called_once_with("device_001", "down", 1000)

    async def test_swipe_rejects_direction_coordinate_conflict(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result
    ):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.swipe(direction="up", from_x=1, from_y=2, to_x=3, to_y=4))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "PARAM_CONFLICT"


class TestInputText:
    async def test_input_rejects_json_string_handle(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(
            await ui.input_text(element_handle='{"window_id":1,"id":"btn_login"}', text="Hello World")
        )

        assert sc["ok"] is False
        assert sc["error"]["code"] == "INVALID_ELEMENT_HANDLE"
        assert "Do not pass a JSON string" in sc["error"]["detail"]

    async def test_input_by_coordinates(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.input_text(x=100, y=200, text="Hello World"))

        assert sc["ok"] is True
        assert sc["result"]["message"] == "input text succeeded"
        assert sc["result"]["resolved_via"] == "coordinates"
        assert sc["result"]["mode"] == "replace"
        assert sc["result"]["verified"] is False
        mock_ui_operations.replace_text.assert_called_once_with("device_001", 100, 200, "Hello World")

    async def test_input_can_append_text(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result
    ):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.input_text(x=100, y=200, text="Hello", mode="append"))

        assert sc["ok"] is True
        assert sc["result"]["mode"] == "append"
        mock_ui_operations.input_text.assert_called_once_with("device_001", 100, 200, "Hello")

    async def test_input_by_lookup(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.input_text(element_type="TextInput", text="Hello World"))

        assert sc["ok"] is True
        assert sc["result"]["resolved_via"] == "search"
        mock_ui_operations.find_element.assert_called_once()
        mock_ui_operations.replace_text.assert_called_once()

    async def test_input_by_element_id(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.input_text(element_id="btn_login", text="Hello World"))

        assert sc["ok"] is True
        assert sc["result"]["resolved_via"] == "search"

    async def test_input_by_handle(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        initial = deepcopy(mock_ui_operations.find_element.return_value)
        updated = deepcopy(initial)
        updated["elements"][0]["text"] = "Hello World"
        mock_ui_operations.find_element.side_effect = [initial, updated]

        sc = unwrap_result(await ui.input_text(element_handle=_sample_handle(), text="Hello World"))

        assert sc["ok"] is True
        assert sc["result"]["resolved_via"] == "handle"
        assert sc["result"]["handle_refreshed"] is False
        assert sc["result"]["verified"] is True
        assert sc["result"]["actual_text"] == "Hello World"
        mock_ui_operations.replace_text.assert_called_once_with("device_001", 100, 200, "Hello World")

    async def test_input_by_handle_rejects_false_command_success(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result
    ):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.input_text(element_handle=_sample_handle(), text="Hello World"))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "TEXT_VERIFICATION_FAILED"
        assert sc["result"]["verified"] is False
        assert sc["result"]["actual_text"] == "Button"

    async def test_input_requires_text(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.input_text(x=100, y=200, text=None))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "MISSING_TEXT"

    async def test_input_requires_target(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.input_text(text="Hello World"))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "MISSING_PARAMS"

    async def test_input_lookup_not_found_is_actionable(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        mock_ui_operations.find_element.return_value = {"success": True, "elements": [], "count": 0}

        sc = unwrap_result(await ui.input_text(element_type="TextInput", text="Hello World"))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "ELEMENT_NOT_FOUND"
        assert "pass its element_handle" in sc["error"]["detail"]

    async def test_input_rejects_coordinate_conflict(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result
    ):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.input_text(x=100, y=200, text="Hello", element_handle=_sample_handle()))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "PARAM_CONFLICT"


class TestPressKey:
    async def test_press_home(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.press_key(key="Home"))

        assert sc["ok"] is True
        assert sc["result"]["message"] == "key press succeeded"
        assert sc["result"]["key"] == "KEYCODE_HOME"
        assert sc["result"]["key_code"] == 1
        assert sc["result"]["modifiers"] == []
        assert sc["result"]["event_key_codes"] == [1]
        assert "action" not in sc["result"]
        mock_ui_operations.press_key.assert_called_once_with("device_001", 1)

    async def test_press_key_rejects_empty_key(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result
    ):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.press_key(key=""))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "INVALID_KEY"

    async def test_press_key_normalizes_common_aliases(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result
    ):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.press_key(key="volume_down"))

        assert sc["ok"] is True
        assert sc["result"]["key"] == "KEYCODE_VOLUME_DOWN"
        assert sc["result"]["key_code"] == 17
        assert sc["result"]["modifiers"] == []
        mock_ui_operations.press_key.assert_called_once_with("device_001", 17)

    async def test_press_key_normalizes_system_key_case_and_separators(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result
    ):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.press_key(key="dpad_up"))

        assert sc["ok"] is True
        assert sc["result"]["key"] == "KEYCODE_DPAD_UP"
        assert sc["result"]["key_code"] == 2012
        mock_ui_operations.press_key.assert_called_once_with("device_001", 2012)

    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("Tab", 2049),
            ("KEYCODE_PAGE_UP", 2068),
            ("page-up", 2068),
            ("F24", 2827),
            ("button a", 2301),
            ("fingerprint_slide_down", 3234),
            ("Backspace", 2055),
            ("Delete", 2071),
        ],
    )
    async def test_press_key_accepts_complete_official_names_and_friendly_aliases(
        self,
        mock_hdc: MagicMock,
        mock_ui_operations: MagicMock,
        unwrap_result,
        key: str,
        expected: int,
    ):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.press_key(key=key))

        assert sc["ok"] is True
        assert sc["result"]["key_code"] == expected
        assert sc["result"]["key"].startswith("KEYCODE_")
        mock_ui_operations.press_key.assert_called_once_with("device_001", expected)

    async def test_press_key_supports_named_modifiers(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result
    ):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.press_key(key="V", modifiers=["Ctrl"]))

        assert sc["ok"] is True
        assert sc["result"]["key"] == "KEYCODE_V"
        assert sc["result"]["key_code"] == 2038
        assert sc["result"]["modifiers"] == ["Ctrl"]
        assert sc["result"]["event_key_codes"] == [2072, 2038]
        mock_ui_operations.send_key_event.assert_called_once_with("device_001", [2072, 2038])

    async def test_press_key_rejects_raw_shell_string(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result
    ):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.press_key(key="2072 2038"))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "INVALID_KEY"
        mock_ui_operations.send_key_event.assert_not_called()

    async def test_press_key_supports_meta_modifier(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result
    ):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.press_key(key="S", modifiers=["Meta"]))

        assert sc["ok"] is True
        assert sc["result"]["modifiers"] == ["Meta"]
        assert sc["result"]["event_key_codes"] == [2076, 2035]

    async def test_press_key_rejects_more_than_two_modifiers(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result
    ):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(
            await ui.press_key(key="S", modifiers=["Ctrl", "Alt", "Shift"])
        )

        assert sc["ok"] is False
        assert sc["error"]["code"] == "INVALID_MODIFIER_COUNT"

    async def test_press_key_rejects_unknown_numeric_keycode(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result
    ):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.press_key(key=65535))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "INVALID_KEY"
        assert sc["result"] == {
            "key": None,
            "key_code": None,
            "modifiers": [],
            "event_key_codes": [],
        }

    async def test_press_key_rejects_duplicate_modifiers(
        self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result
    ):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.press_key(key="V", modifiers=["Ctrl", "Ctrl"]))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "DUPLICATE_MODIFIER"


class TestFindElements:
    async def test_find_by_text(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.find_elements(text="登录"))

        assert sc["ok"] is True
        assert sc["result"]["count"] == 1
        mock_ui_operations.find_element.assert_called_once()

    async def test_find_by_type(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.find_elements(element_type="Button"))

        assert sc["ok"] is True
        assert sc["result"]["elements"][0]["lookup_is_broad"] is True
        mock_ui_operations.find_element.assert_called_once()

    async def test_find_includes_handle_metadata(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.find_elements(text="Button", bundle_name="com.example.app"))

        assert sc["ok"] is True
        element = sc["result"]["elements"][0]
        assert element["element_handle"]["compid"] == "comp_btn_login"
        assert element["element_handle"]["lookup_hint"]["text"] == "Button"
        assert element["lookup_is_broad"] is False
        assert "lookup_hint" not in element
        assert element["bounds"]["left"] == 80

    async def test_find_requires_criteria(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.find_elements())

        assert sc["ok"] is False
        assert sc["error"]["code"] == "MISSING_SEARCH_CRITERIA"

    async def test_find_returns_not_found_when_empty(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        mock_ui_operations.find_element.return_value = {"success": True, "elements": [], "count": 0}

        sc = unwrap_result(await ui.find_elements(text="missing"))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "ELEMENT_NOT_FOUND"
        assert sc["result"]["count"] == 0


class TestLongPressElement:
    async def test_long_press_by_handle(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.long_press(element_handle=_sample_handle()))

        assert sc["ok"] is True
        assert sc["result"]["resolved_via"] == "handle"
        mock_ui_operations.long_click.assert_called_once_with("device_001", 100, 200)

    async def test_long_press_by_element_id(self, mock_hdc: MagicMock, mock_ui_operations: MagicMock, unwrap_result):
        from harmonyos_dev_mcp.tools import ui

        sc = unwrap_result(await ui.long_press(element_id="btn_login"))

        assert sc["ok"] is True
        assert sc["result"]["resolved_via"] == "search"


class TestScreenshot:
    async def test_screenshot_rejects_partial_bounds(self, mock_hdc: MagicMock, unwrap_result, monkeypatch):
        from harmonyos_dev_mcp.tools import ui

        monkeypatch.setattr(ui, "get_hdc", lambda: mock_hdc)
        sc = unwrap_result(await ui.screenshot(left=0, top=0, right=100))

        assert sc["ok"] is False
        assert sc["error"]["code"] == "PARAM_CONFLICT"
