from unittest.mock import patch

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
