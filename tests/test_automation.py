from unittest.mock import patch

import pytest

from adb import automation, manager
from adb.automation import MAX_MACRO_STEPS, MAX_MACRO_WAIT_MS, validate_macro_steps


def test_validate_macro_steps_accepts_known_types():
    steps = [{"type": "tap", "x": 1, "y": 2}, {"type": "wait", "wait_ms": 100}, {"type": "text", "text": "hi"}]
    validate_macro_steps(steps)  # should not raise


def test_validate_macro_steps_rejects_unknown_type():
    with pytest.raises(manager.AdbError):
        validate_macro_steps([{"type": "launch_nuclear_missiles"}])


def test_validate_macro_steps_rejects_too_many_steps():
    steps = [{"type": "tap", "x": 0, "y": 0}] * (MAX_MACRO_STEPS + 1)
    with pytest.raises(manager.AdbError):
        validate_macro_steps(steps)


def test_validate_macro_steps_rejects_excessive_wait():
    steps = [{"type": "wait", "wait_ms": MAX_MACRO_WAIT_MS + 1}]
    with pytest.raises(manager.AdbError):
        validate_macro_steps(steps)


def test_tap_swipe_long_press_command_construction():
    with patch("adb.automation.manager.shell", return_value=("", "", 0)) as mock_shell:
        automation.tap("s1", 10, 20)
    assert mock_shell.call_args[0][1] == "input tap 10 20"

    with patch("adb.automation.manager.shell", return_value=("", "", 0)) as mock_shell:
        automation.swipe("s1", 1, 2, 3, 4, duration_ms=500)
    assert mock_shell.call_args[0][1] == "input swipe 1 2 3 4 500"

    with patch("adb.automation.swipe", return_value={"ok": True}) as mock_swipe:
        automation.long_press("s1", 5, 6, duration_ms=900)
    mock_swipe.assert_called_once_with("s1", 5, 6, 5, 6, 900)


def test_type_text_converts_spaces_and_quotes():
    with patch("adb.automation.manager.shell", return_value=("", "", 0)) as mock_shell:
        automation.type_text("s1", "hello world")
    assert mock_shell.call_args[0][1] == "input text hello%sworld"

    # shlex.quote wraps in single quotes only when the text still contains
    # shell-special characters after the space->%s substitution.
    with patch("adb.automation.manager.shell", return_value=("", "", 0)) as mock_shell:
        automation.type_text("s1", "a; rm -rf /")
    assert mock_shell.call_args[0][1] == "input text 'a;%srm%s-rf%s/'"


def test_get_screen_size_parses_override_and_physical():
    with patch("adb.automation.manager.shell", return_value=("Physical size: 1080x1920\n", "", 0)):
        assert automation.get_screen_size("s1") == {"width": 1080, "height": 1920}
    with patch("adb.automation.manager.shell", return_value=("Physical size: 1080x1920\nOverride size: 720x1280\n", "", 0)):
        assert automation.get_screen_size("s1") == {"width": 1080, "height": 1920}


def test_get_screen_size_none_on_failure_or_no_match():
    with patch("adb.automation.manager.shell", return_value=("", "err", 1)):
        assert automation.get_screen_size("s1") == {"width": None, "height": None}
    with patch("adb.automation.manager.shell", return_value=("garbage", "", 0)):
        assert automation.get_screen_size("s1") == {"width": None, "height": None}


def test_keyevent_valid_and_invalid_code():
    with patch("adb.automation.manager.shell", return_value=("", "", 0)) as mock_shell:
        result = automation.keyevent("s1", "KEYCODE_HOME")
    assert result == {"ok": True}
    assert mock_shell.call_args[0][1] == "input keyevent KEYCODE_HOME"

    result = automation.keyevent("s1", "; rm -rf /")
    assert result == {"ok": False, "error": "invalid_keycode"}


def test_play_macro_runs_steps_and_reports_overall_ok():
    steps = [{"type": "tap", "x": 1, "y": 2}, {"type": "wait", "wait_ms": 1}]
    with patch("adb.automation.time.sleep") as mock_sleep, \
         patch("adb.automation.tap", return_value={"ok": True}):
        result = automation.play_macro("s1", steps)
    assert result["ok"] is True
    assert result["results"][0] == {"type": "tap", "ok": True}
    assert result["results"][1] == {"type": "wait", "ok": True}
    mock_sleep.assert_called_once_with(0.001)


def test_play_macro_reports_failure_when_any_step_fails():
    steps = [{"type": "tap", "x": 1, "y": 2}]
    with patch("adb.automation.tap", return_value={"ok": False}):
        result = automation.play_macro("s1", steps)
    assert result["ok"] is False


def test_play_macro_rejects_invalid_steps_before_running():
    with pytest.raises(manager.AdbError):
        automation.play_macro("s1", [{"type": "not_a_real_step"}])


def test_list_macros_delegates_to_config(monkeypatch):
    monkeypatch.setattr(automation.config, "load_macros", lambda: {"a": []})
    assert automation.list_macros() == {"a": []}


def test_save_macro_success(monkeypatch):
    saved = {}
    monkeypatch.setattr(automation.config, "load_macros", lambda: {})
    monkeypatch.setattr(automation.config, "save_macros", lambda m: saved.update(m))
    result = automation.save_macro("my macro", [{"type": "tap", "x": 1, "y": 2}])
    assert result == {"ok": True}
    assert "my macro" in saved


def test_save_macro_rejects_empty_or_non_string_name(monkeypatch):
    monkeypatch.setattr(automation.config, "load_macros", lambda: {})
    for bad_name in ["", "   ", None, 123, "x" * (automation.MAX_MACRO_NAME_LEN + 1)]:
        with pytest.raises(manager.AdbError):
            automation.save_macro(bad_name, [])


def test_delete_macro_removes_existing_and_is_idempotent(monkeypatch):
    store = {"a": []}
    monkeypatch.setattr(automation.config, "load_macros", lambda: store)
    monkeypatch.setattr(automation.config, "save_macros", lambda m: store.update(m))
    assert automation.delete_macro("a") == {"ok": True}
    assert "a" not in store
    assert automation.delete_macro("does-not-exist") == {"ok": True}
