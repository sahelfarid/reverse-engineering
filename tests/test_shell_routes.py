import json
from unittest.mock import patch

from adb import manager as adb_manager


def test_su_available_success(auth_client):
    with patch("routes.shell.adb_shell.su_available", return_value=True):
        res = auth_client.get("/api/devices/s1/shell/su-available")
    assert res.status_code == 200
    assert res.get_json()["available"] is True


def test_su_available_maps_adb_error(auth_client):
    with patch("routes.shell.adb_shell.su_available", side_effect=adb_manager.AdbError("bad serial")):
        res = auth_client.get("/api/devices/s1/shell/su-available")
    assert res.status_code == 400


def test_shell_exec_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    res = client.post("/api/devices/s1/shell/exec", data=json.dumps({"command": "id"}), content_type="application/json")
    assert res.status_code == 403


def test_shell_exec_success_and_audit_log(auth_client):
    with patch("routes.shell.adb_shell.run_command", return_value={"stdout": "ok", "stderr": "", "returncode": 0}), \
         patch("routes.shell.auth.audit_log") as mock_audit:
        res = auth_client.post(
            "/api/devices/s1/shell/exec",
            data=json.dumps({"command": "id", "use_su": True}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    assert res.get_json()["result"]["stdout"] == "ok"
    mock_audit.assert_called_once()
    action, details = mock_audit.call_args[0]
    assert action == "shell_exec"
    assert details["use_su"] is True
    assert details["command"] == "id"
    assert details["returncode"] == 0


def test_shell_exec_maps_adb_not_installed(auth_client):
    with patch("routes.shell.adb_shell.run_command", side_effect=adb_manager.AdbNotInstalledError("no adb")):
        res = auth_client.post(
            "/api/devices/s1/shell/exec",
            data=json.dumps({"command": "id"}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 503


def test_shell_exec_truncates_long_command_in_audit_log(auth_client):
    long_command = "x" * 1000
    with patch("routes.shell.adb_shell.run_command", return_value={"stdout": "", "stderr": "", "returncode": 0}), \
         patch("routes.shell.auth.audit_log") as mock_audit:
        auth_client.post(
            "/api/devices/s1/shell/exec",
            data=json.dumps({"command": long_command}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    _, details = mock_audit.call_args[0]
    assert len(details["command"]) == 500
