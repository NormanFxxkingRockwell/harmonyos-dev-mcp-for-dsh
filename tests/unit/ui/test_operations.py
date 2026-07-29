import shlex

from harmonyos_dev_mcp.ui.keycodes import (
    KEY_CODE_BY_NAME,
    KeyCode,
    key_code_for_digit,
    key_code_for_letter,
    resolve_key,
)
from harmonyos_dev_mcp.ui.operations import UiTestWrapper


class _RecordingHdc:
    def __init__(self):
        self.commands = []

    def execute_shell(self, device_id, command, timeout=None):
        self.commands.append((device_id, command, timeout))
        return {"success": True, "stdout": "", "stderr": "", "returncode": 0}


def test_keycodes_include_complete_sdk_catalog():
    assert len(KEY_CODE_BY_NAME) == 354
    assert KEY_CODE_BY_NAME["KEYCODE_CTRL_LEFT"] == 2072
    assert int(KeyCode.CTRL_LEFT) == 2072
    assert int(KeyCode.MOVE_END) == 2082
    assert int(KeyCode.F24) == 2827
    assert int(KeyCode.FINGERPRINT_SLIDE_DOWN) == 3234
    assert key_code_for_letter("a") == 2017
    assert key_code_for_letter("z") == 2042
    assert key_code_for_digit("0") == 2000
    assert key_code_for_digit("9") == 2009


def test_keycode_resolution_accepts_official_forms_and_clear_aliases():
    assert resolve_key("Tab").name == "KEYCODE_TAB"
    assert resolve_key("KEYCODE_TAB").code == 2049
    assert resolve_key("page-up").code == 2068
    assert resolve_key("Backspace").name == "KEYCODE_DEL"
    assert resolve_key("Delete").name == "KEYCODE_FORWARD_DEL"
    assert resolve_key("DEL").code == 2055
    assert resolve_key(2622).name == "KEYCODE_PASTE"
    assert resolve_key(65535) is None
    assert resolve_key("１２") is None
    assert resolve_key("not-a-real-key") is None


def test_input_text_quotes_utf8_and_shell_characters():
    hdc = _RecordingHdc()
    wrapper = UiTestWrapper(hdc)
    text = "O'Reilly; 中文 | $HOME"

    result = wrapper.input_text("device_001", 10, 20, text)

    assert result["success"] is True
    assert [command for _, command, _ in hdc.commands] == [
        "uitest uiInput click 10 20",
        "uitest uiInput keyEvent 2082",
        f"uitest uiInput text {shlex.quote(text)}",
    ]


def test_send_key_event_emits_one_key_event():
    hdc = _RecordingHdc()
    wrapper = UiTestWrapper(hdc)

    result = wrapper.send_key_event("device_001", [2072, 2038])

    assert result["success"] is True
    assert result["keys"] == [2072, 2038]
    assert hdc.commands[-1][1] == "uitest uiInput keyEvent 2072 2038"


def test_replace_text_selects_existing_value_and_inputs_without_preclearing():
    hdc = _RecordingHdc()
    wrapper = UiTestWrapper(hdc)

    result = wrapper.replace_text("device_001", 10, 20, "新内容")

    assert result["success"] is True
    assert [command for _, command, _ in hdc.commands] == [
        "uitest uiInput click 10 20",
        "uitest uiInput keyEvent 2072 2017",
        f"uitest uiInput text {shlex.quote('新内容')}",
    ]


def test_replace_text_with_empty_value_only_clears():
    hdc = _RecordingHdc()
    wrapper = UiTestWrapper(hdc)

    result = wrapper.replace_text("device_001", 10, 20, "")

    assert result["success"] is True
    assert [command for _, command, _ in hdc.commands] == [
        "uitest uiInput click 10 20",
        "uitest uiInput keyEvent 2072 2017",
        "uitest uiInput keyEvent 2071",
    ]


def test_find_element_in_tree_filters_global_dump_by_window_id():
    wrapper = UiTestWrapper(_RecordingHdc())
    tree = {
        "nodes": [
            {
                "type": "TextInput",
                "properties": {
                    "ID": "security",
                    "compid": "92:security",
                    "text": "security",
                    "left": 10,
                    "top": 20,
                    "width": 100,
                    "height": 40,
                },
                "children": [],
            },
            {
                "type": "TextInput",
                "properties": {
                    "ID": "browser",
                    "compid": "100:browser",
                    "text": "browser",
                    "left": 200,
                    "top": 20,
                    "width": 100,
                    "height": 40,
                },
                "children": [],
            },
        ]
    }

    elements = wrapper.find_element_in_tree(
        tree,
        element_type="TextInput",
        window_id=92,
    )

    assert [element["id"] for element in elements] == ["security"]
    assert elements[0]["window_id"] == 92
