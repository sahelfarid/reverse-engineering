from unittest.mock import patch

import pytest

from adb import root_detection


def test_summarize_all_clear():
    indicators = {
        "working_root_shell": False, "su_paths": [], "busybox": None,
        "magisk": {"app_installed": False, "artifacts": []},
        "build_integrity": {"build_tags": "release-keys", "debuggable": "0", "secure": "1",
                             "verified_boot_state": "green", "bootloader_locked": "1", "selinux": "Enforcing"},
    }
    result = root_detection.summarize(indicators)
    assert result["verdict"] == "not detected"
    assert result["matched_indicators"] == []


def test_summarize_working_root_is_rooted():
    indicators = {"working_root_shell": True, "su_paths": [], "busybox": None,
                  "magisk": {"app_installed": False, "artifacts": []}, "build_integrity": {}}
    result = root_detection.summarize(indicators)
    assert result["verdict"] == "rooted"
    assert any("Working root shell" in m for m in result["matched_indicators"])


def test_summarize_su_binary_only_is_likely_rooted():
    indicators = {"working_root_shell": False, "su_paths": ["/system/xbin/su"], "busybox": None,
                  "magisk": {"app_installed": False, "artifacts": []}, "build_integrity": {}}
    result = root_detection.summarize(indicators)
    assert result["verdict"] == "likely rooted"


def test_summarize_magisk_app_only_is_likely_rooted():
    indicators = {"working_root_shell": False, "su_paths": [], "busybox": None,
                  "magisk": {"app_installed": True, "artifacts": []}, "build_integrity": {}}
    assert root_detection.summarize(indicators)["verdict"] == "likely rooted"


def test_summarize_weak_signals_only_is_possibly_modified():
    indicators = {"working_root_shell": False, "su_paths": [], "busybox": None,
                  "magisk": {"app_installed": False, "artifacts": []},
                  "build_integrity": {"build_tags": "test-keys", "debuggable": "1", "secure": "0",
                                       "selinux": "Permissive", "bootloader_locked": "0"}}
    result = root_detection.summarize(indicators)
    assert result["verdict"] == "possibly modified"
    assert any("test-keys" in m for m in result["matched_indicators"])
    assert any("Bootloader unlocked" in m for m in result["matched_indicators"])


def test_check_build_integrity_parses_key_value_output():
    sample = ("build_tags=release-keys\ndebuggable=0\nsecure=1\n"
              "verified_boot_state=green\nbootloader_locked=1\nselinux=Enforcing")
    with patch("adb.root_detection.manager.shell", return_value=(sample, "", 0)):
        result = root_detection.check_build_integrity("emulator-5554")
    assert result["build_tags"] == "release-keys"
    assert result["selinux"] == "Enforcing"
    assert result["bootloader_locked"] == "1"


def test_check_build_integrity_partial_output_does_not_null_everything():
    # Only some getprop calls returned values; the rest should be None, not an error.
    sample = "build_tags=test-keys\ndebuggable=\nselinux=Permissive"
    with patch("adb.root_detection.manager.shell", return_value=(sample, "", 0)):
        result = root_detection.check_build_integrity("emulator-5554")
    assert result["build_tags"] == "test-keys"
    assert result["debuggable"] is None
    assert result["selinux"] == "Permissive"


def test_check_su_paths_returns_matched_lines():
    with patch("adb.root_detection.manager.shell", return_value=("/system/xbin/su\n/su/bin/su\n", "", 0)):
        result = root_detection.check_su_paths("emulator-5554")
    assert result == ["/system/xbin/su", "/su/bin/su"]


def test_check_magisk_detects_installed_app():
    with patch("adb.root_detection.manager.shell") as mock_shell:
        mock_shell.side_effect = [
            ("package:/data/app/magisk.apk", "", 0),  # pm path
            ("/data/adb/magisk\n", "", 0),             # artifact check
        ]
        result = root_detection.check_magisk("emulator-5554")
    assert result["app_installed"] is True
    assert "/data/adb/magisk" in result["artifacts"]


def test_check_magisk_not_installed():
    with patch("adb.root_detection.manager.shell") as mock_shell:
        mock_shell.side_effect = [("", "not found", 1), ("", "", 0)]
        result = root_detection.check_magisk("emulator-5554")
    assert result == {"app_installed": False, "artifacts": []}


def test_check_busybox_found_and_not_found():
    with patch("adb.root_detection.manager.shell", return_value=("/system/xbin/busybox\n", "", 0)):
        assert root_detection.check_busybox("emulator-5554") == "/system/xbin/busybox"
    with patch("adb.root_detection.manager.shell", return_value=("", "not found", 1)):
        assert root_detection.check_busybox("emulator-5554") is None
    with patch("adb.root_detection.manager.shell", return_value=("", "", 0)):
        assert root_detection.check_busybox("emulator-5554") is None


def test_summarize_busybox_only_is_weak_signal():
    indicators = {"working_root_shell": False, "su_paths": [], "busybox": "/system/xbin/busybox",
                  "magisk": {"app_installed": False, "artifacts": []}, "build_integrity": {}}
    result = root_detection.summarize(indicators)
    assert result["verdict"] == "possibly modified"
    assert any("busybox present" in m for m in result["matched_indicators"])


def test_get_integrity_report_orchestrates_all_checks():
    with patch("adb.root_detection.manager.validate_serial", return_value="s1"), \
         patch("adb.root_detection.check_su_paths", return_value=["/system/xbin/su"]) as m1, \
         patch("adb.root_detection.check_magisk", return_value={"app_installed": False, "artifacts": []}) as m2, \
         patch("adb.root_detection.check_busybox", return_value=None) as m3, \
         patch("adb.root_detection.check_build_integrity", return_value={}) as m4, \
         patch("adb.root_detection.manager.has_root_shell", return_value=False) as m5:
        report = root_detection.get_integrity_report("s1")
    assert report["verdict"] == "likely rooted"
    assert report["indicators"]["su_paths"] == ["/system/xbin/su"]
    assert "Play Integrity" in report["disclaimer"]
    for mock in (m1, m2, m3, m4, m5):
        mock.assert_called_once_with("s1")


def test_get_integrity_report_validates_serial_first():
    with patch("adb.root_detection.manager.validate_serial", side_effect=root_detection.manager.AdbError("bad serial")):
        with pytest.raises(root_detection.manager.AdbError):
            root_detection.get_integrity_report("; rm -rf /")
