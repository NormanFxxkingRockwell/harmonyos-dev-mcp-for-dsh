import shlex

from harmonyos_dev_mcp.ui.operations import UiTestWrapper


class _RecordingHdc:
    def __init__(self):
        self.commands = []

    def execute_shell(self, device_id, command, timeout=None):
        self.commands.append((device_id, command, timeout))
        return {"success": True, "stdout": "", "stderr": "", "returncode": 0}


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
        "uitest uiInput keyEvent 2047",
        "uitest uiInput keyEvent 2047",
    ]


def test_send_key_event_emits_one_key_event():
    hdc = _RecordingHdc()
    wrapper = UiTestWrapper(hdc)

    result = wrapper.send_key_event("device_001", [2072, 2038])

    assert result["success"] is True
    assert result["keys"] == [2072, 2038]
    assert hdc.commands[-1][1] == "uitest uiInput keyEvent 2072 2038"


def test_replace_text_focuses_clears_and_inputs():
    hdc = _RecordingHdc()
    wrapper = UiTestWrapper(hdc)

    result = wrapper.replace_text("device_001", 10, 20, "新内容")

    assert result["success"] is True
    assert [command for _, command, _ in hdc.commands] == [
        "uitest uiInput click 10 20",
        "uitest uiInput keyEvent 2072 2017",
        "uitest uiInput keyEvent 2071",
        f"uitest uiInput text {shlex.quote('新内容')}",
        "uitest uiInput keyEvent 2047",
        "uitest uiInput keyEvent 2047",
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
