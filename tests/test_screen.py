from unittest.mock import MagicMock, patch

import pytest

from adb import manager, screen


@pytest.fixture(autouse=True)
def clear_active_recordings():
    screen._ACTIVE_RECORDINGS.clear()
    yield
    screen._ACTIVE_RECORDINGS.clear()


def test_take_screenshot_success():
    fake_proc = MagicMock(returncode=0, stdout=b"\x89PNG...")
    with patch("adb.screen.manager.validate_serial", return_value="s1"), \
         patch("adb.screen.manager.run_binary", return_value=fake_proc):
        assert screen.take_screenshot("s1") == b"\x89PNG..."


def test_take_screenshot_raises_on_failure_or_empty_output():
    fake_proc = MagicMock(returncode=1, stdout=b"")
    with patch("adb.screen.manager.validate_serial", return_value="s1"), \
         patch("adb.screen.manager.run_binary", return_value=fake_proc):
        with pytest.raises(manager.AdbError):
            screen.take_screenshot("s1")

    fake_proc_empty = MagicMock(returncode=0, stdout=b"")
    with patch("adb.screen.manager.validate_serial", return_value="s1"), \
         patch("adb.screen.manager.run_binary", return_value=fake_proc_empty):
        with pytest.raises(manager.AdbError):
            screen.take_screenshot("s1")


def test_start_recording_success():
    with patch("adb.screen.manager.validate_serial", return_value="s1"), \
         patch("adb.screen.manager.shell", return_value=("12345\n", "", 0)):
        result = screen.start_recording("s1", time_limit_sec=60)
    assert result == {"ok": True, "pid": "12345", "remote_path": "/sdcard/adbpanel_record.mp4"}
    assert screen._ACTIVE_RECORDINGS["s1"]["pid"] == "12345"


def test_start_recording_rejects_when_already_active():
    screen._ACTIVE_RECORDINGS["s1"] = {"pid": "1", "remote_path": "/x"}
    with patch("adb.screen.manager.validate_serial", return_value="s1"):
        result = screen.start_recording("s1")
    assert result == {"ok": False, "error": "recording_already_active"}


def test_start_recording_fails_when_pid_not_digit():
    with patch("adb.screen.manager.validate_serial", return_value="s1"), \
         patch("adb.screen.manager.shell", return_value=("not-a-pid\n", "", 0)):
        result = screen.start_recording("s1")
    assert result == {"ok": False, "error": "failed_to_start"}
    assert "s1" not in screen._ACTIVE_RECORDINGS


def test_stop_recording_success():
    screen._ACTIVE_RECORDINGS["s1"] = {"pid": "12345", "remote_path": "/sdcard/rec.mp4"}
    with patch("adb.screen.manager.shell", return_value=("", "", 0)) as mock_shell:
        result = screen.stop_recording("s1")
    assert result == {"ok": True, "remote_path": "/sdcard/rec.mp4"}
    assert "s1" not in screen._ACTIVE_RECORDINGS
    assert "kill -INT 12345" in mock_shell.call_args[0][1]


def test_stop_recording_no_active_recording():
    assert screen.stop_recording("s1") == {"ok": False, "error": "no_active_recording"}


def test_recording_status_active_and_inactive():
    assert screen.recording_status("s1") == {"active": False, "remote_path": None}
    screen._ACTIVE_RECORDINGS["s1"] = {"pid": "1", "remote_path": "/x.mp4"}
    assert screen.recording_status("s1") == {"active": True, "remote_path": "/x.mp4"}


def test_set_rotation_valid_and_invalid():
    with patch("adb.screen.manager.shell", return_value=("", "", 0)) as mock_shell:
        result = screen.set_rotation("s1", 90)
    assert result == {"ok": True}
    assert "user_rotation 1" in mock_shell.call_args[0][1]

    result = screen.set_rotation("s1", 45)
    assert result == {"ok": False, "error": "invalid_rotation"}


def test_unlock_auto_rotation_wake_sleep():
    with patch("adb.screen.manager.shell", return_value=("", "", 0)):
        assert screen.unlock_auto_rotation("s1") == {"ok": True}
        assert screen.wake_device("s1") == {"ok": True}
        assert screen.sleep_device("s1") == {"ok": True}
    with patch("adb.screen.manager.shell", return_value=("", "err", 1)):
        assert screen.unlock_auto_rotation("s1") == {"ok": False}


def test_set_brightness_clamps_range():
    with patch("adb.screen.manager.shell", return_value=("", "", 0)) as mock_shell:
        screen.set_brightness("s1", 500)
    assert "screen_brightness 255" in mock_shell.call_args[0][1]

    with patch("adb.screen.manager.shell", return_value=("", "", 0)) as mock_shell:
        screen.set_brightness("s1", -10)
    assert "screen_brightness 0" in mock_shell.call_args[0][1]
