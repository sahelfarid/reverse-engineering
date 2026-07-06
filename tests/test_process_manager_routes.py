import json
from unittest.mock import patch

from adb import manager as adb_manager


def test_list_processes_success(auth_client):
    with patch("routes.process_manager.adb_process_manager.list_processes", return_value={"processes": [], "parseable": True}):
        res = auth_client.get("/api/devices/s1/processes")
    assert res.status_code == 200


def test_list_processes_maps_adb_not_installed(auth_client):
    with patch("routes.process_manager.adb_process_manager.list_processes", side_effect=adb_manager.AdbNotInstalledError("x")):
        res = auth_client.get("/api/devices/s1/processes")
    assert res.status_code == 503


def test_foreground_app_success(auth_client):
    with patch("routes.process_manager.adb_process_manager.get_foreground_app", return_value={"package": "com.example.app"}):
        res = auth_client.get("/api/devices/s1/foreground-app")
    assert res.status_code == 200


def test_kill_process_success_and_audit_log(auth_client):
    with patch("routes.process_manager.adb_process_manager.kill_process", return_value={"ok": True}) as mock_kill, \
         patch("routes.process_manager.auth.audit_log") as mock_audit:
        res = auth_client.post(
            "/api/devices/s1/processes/1234/kill",
            data=json.dumps({"signal": "KILL"}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    mock_kill.assert_called_once_with("s1", 1234, "KILL")
    mock_audit.assert_called_once_with("process_kill", {"serial": "s1", "pid": 1234, "signal": "KILL"})


def test_kill_process_defaults_to_term_signal(auth_client):
    with patch("routes.process_manager.adb_process_manager.kill_process", return_value={"ok": True}) as mock_kill, \
         patch("routes.process_manager.auth.audit_log"):
        auth_client.post(
            "/api/devices/s1/processes/1234/kill",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    mock_kill.assert_called_once_with("s1", 1234, "TERM")


def test_kill_process_maps_adb_error(auth_client):
    with patch("routes.process_manager.adb_process_manager.kill_process", side_effect=adb_manager.AdbError("bad")):
        res = auth_client.post("/api/devices/s1/processes/1234/kill", headers={"X-CSRF-Token": auth_client.csrf_token})
    assert res.status_code == 400


def test_kill_process_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    res = client.post("/api/devices/s1/processes/1234/kill")
    assert res.status_code == 403


def test_kill_process_rejects_non_numeric_pid_at_route_level(auth_client):
    # Flask's <int:pid> URL converter rejects this before the view ever runs
    # -- this is why kill_process()'s own int(pid) coercion is unreachable
    # with a malformed value through this route (see backend audit notes).
    res = auth_client.post(
        "/api/devices/s1/processes/not-a-pid/kill", headers={"X-CSRF-Token": auth_client.csrf_token}
    )
    assert res.status_code == 404


def test_process_routes_require_login(client):
    assert client.get("/api/devices/s1/processes").status_code == 401
    assert client.get("/api/devices/s1/foreground-app").status_code == 401
