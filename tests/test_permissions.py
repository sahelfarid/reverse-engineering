from unittest.mock import patch

import pytest

from adb import manager, permissions


def test_validate_permission_accepts_standard_and_custom_names():
    assert permissions.validate_permission("android.permission.CAMERA") == "android.permission.CAMERA"
    assert permissions.validate_permission("com.example.app.permission.CUSTOM") == "com.example.app.permission.CUSTOM"


def test_validate_permission_rejects_empty_and_shell_metacharacters():
    for bad in ["", "; rm -rf /", "android.permission.CAMERA; rm -rf /", "`whoami`"]:
        with pytest.raises(manager.AdbError):
            permissions.validate_permission(bad)


def test_get_permission_detail_classifies_dangerous_and_normal():
    fake_perms = {
        "requested": ["android.permission.CAMERA", "android.permission.INTERNET"],
        "granted": ["android.permission.INTERNET"],
        "denied": ["android.permission.CAMERA"],
    }
    with patch("adb.permissions.packages.validate_package", return_value="com.example.app"), \
         patch("adb.permissions.app_inspector.get_permissions", return_value=fake_perms):
        result = permissions.get_permission_detail("s1", "com.example.app")
    assert result["dangerous_requested"] == ["android.permission.CAMERA"]
    assert result["normal_requested"] == ["android.permission.INTERNET"]
    assert result["granted"] == ["android.permission.INTERNET"]
    assert result["denied"] == ["android.permission.CAMERA"]


def test_grant_permission_success_and_failure_uses_stderr():
    with patch("adb.permissions.packages.validate_package", return_value="com.example.app"), \
         patch("adb.permissions.manager.shell", return_value=("", "", 0)) as mock_shell:
        result = permissions.grant_permission("s1", "com.example.app", "android.permission.CAMERA")
    assert result == {"ok": True, "error": None}
    assert "pm grant" in mock_shell.call_args[0][1]

    with patch("adb.permissions.packages.validate_package", return_value="com.example.app"), \
         patch("adb.permissions.manager.shell", return_value=("", "not allowed", 1)):
        result = permissions.grant_permission("s1", "com.example.app", "android.permission.CAMERA")
    assert result == {"ok": False, "error": "not allowed"}


def test_grant_permission_falls_back_to_stdout_when_stderr_empty():
    # Some Android builds emit failure text on stdout instead of stderr --
    # the fix in this pass makes both routes fall back to stdout.
    with patch("adb.permissions.packages.validate_package", return_value="com.example.app"), \
         patch("adb.permissions.manager.shell", return_value=("Failure: SecurityException", "", 1)):
        result = permissions.grant_permission("s1", "com.example.app", "android.permission.CAMERA")
    assert result == {"ok": False, "error": "Failure: SecurityException"}


def test_revoke_permission_success_and_stdout_fallback():
    with patch("adb.permissions.packages.validate_package", return_value="com.example.app"), \
         patch("adb.permissions.manager.shell", return_value=("", "", 0)):
        result = permissions.revoke_permission("s1", "com.example.app", "android.permission.CAMERA")
    assert result == {"ok": True, "error": None}

    with patch("adb.permissions.packages.validate_package", return_value="com.example.app"), \
         patch("adb.permissions.manager.shell", return_value=("Failure: not granted", "", 1)):
        result = permissions.revoke_permission("s1", "com.example.app", "android.permission.CAMERA")
    assert result == {"ok": False, "error": "Failure: not granted"}


def test_grant_revoke_validate_permission_before_shell_call():
    with patch("adb.permissions.packages.validate_package", return_value="com.example.app"), \
         patch("adb.permissions.manager.shell") as mock_shell:
        with pytest.raises(manager.AdbError):
            permissions.grant_permission("s1", "com.example.app", "; rm -rf /")
    mock_shell.assert_not_called()
