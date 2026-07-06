from unittest.mock import patch

from adb import manager as adb_manager


def test_inspect_success(auth_client):
    with patch("routes.app_inspector.adb_inspector.get_app_detail", return_value={"package": "com.example.app"}):
        res = auth_client.get("/api/devices/s1/packages/com.example.app/inspect")
    assert res.status_code == 200
    assert res.get_json()["detail"] == {"package": "com.example.app"}


def test_inspect_maps_adb_not_installed(auth_client):
    with patch("routes.app_inspector.adb_inspector.get_app_detail", side_effect=adb_manager.AdbNotInstalledError("x")):
        res = auth_client.get("/api/devices/s1/packages/com.example.app/inspect")
    assert res.status_code == 503


def test_inspect_maps_adb_error(auth_client):
    with patch("routes.app_inspector.adb_inspector.get_app_detail", side_effect=adb_manager.AdbError("bad package")):
        res = auth_client.get("/api/devices/s1/packages/com.example.app/inspect")
    assert res.status_code == 400


def test_inspect_requires_login(client):
    assert client.get("/api/devices/s1/packages/com.example.app/inspect").status_code == 401


def test_restart_requires_csrf(client):
    import json
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    res = client.post("/api/devices/s1/packages/com.example.app/restart")
    assert res.status_code == 403


def test_restart_success_and_audit_log(auth_client):
    with patch("routes.app_inspector.adb_packages.restart_app", return_value={"ok": True, "output": ""}), \
         patch("routes.app_inspector.auth.audit_log") as mock_audit:
        res = auth_client.post(
            "/api/devices/s1/packages/com.example.app/restart",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    mock_audit.assert_called_once_with("package_restart", {"serial": "s1", "package": "com.example.app"})


def test_restart_maps_adb_error(auth_client):
    with patch("routes.app_inspector.adb_packages.restart_app", side_effect=adb_manager.AdbError("bad")):
        res = auth_client.post(
            "/api/devices/s1/packages/com.example.app/restart",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 400
