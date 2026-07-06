import json
from unittest.mock import patch

from adb import manager as adb_manager


def _post(auth_client, url, payload=None):
    return auth_client.post(
        url, data=json.dumps(payload if payload is not None else {}), content_type="application/json",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )


def test_permissions_detail_success(auth_client):
    with patch("routes.battery.adb_permissions.get_permission_detail", return_value={"requested": []}):
        res = auth_client.get("/api/devices/s1/packages/com.example.app/permissions")
    assert res.status_code == 200
    assert res.get_json()["permissions"] == {"requested": []}


def test_permissions_detail_maps_adb_error(auth_client):
    with patch("routes.battery.adb_permissions.get_permission_detail", side_effect=adb_manager.AdbError("bad package")):
        res = auth_client.get("/api/devices/s1/packages/com.example.app/permissions")
    assert res.status_code == 400


def test_permissions_grant_success_and_audit_log(auth_client):
    with patch("routes.battery.adb_permissions.grant_permission", return_value={"ok": True, "error": None}), \
         patch("routes.battery.auth.audit_log") as mock_audit:
        res = _post(
            auth_client, "/api/devices/s1/packages/com.example.app/permissions/grant",
            {"permission": "android.permission.CAMERA"},
        )
    assert res.status_code == 200
    mock_audit.assert_called_once_with(
        "permission_grant", {"serial": "s1", "package": "com.example.app", "permission": "android.permission.CAMERA"}
    )


def test_permissions_grant_maps_invalid_permission(auth_client):
    with patch("routes.battery.adb_permissions.grant_permission", side_effect=adb_manager.AdbError("invalid permission name")):
        res = _post(auth_client, "/api/devices/s1/packages/com.example.app/permissions/grant", {"permission": "bad;perm"})
    assert res.status_code == 400


def test_permissions_grant_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    res = client.post("/api/devices/s1/packages/com.example.app/permissions/grant")
    assert res.status_code == 403


def test_permissions_revoke_success_and_audit_log(auth_client):
    with patch("routes.battery.adb_permissions.revoke_permission", return_value={"ok": True, "error": None}), \
         patch("routes.battery.auth.audit_log") as mock_audit:
        res = _post(
            auth_client, "/api/devices/s1/packages/com.example.app/permissions/revoke",
            {"permission": "android.permission.CAMERA"},
        )
    assert res.status_code == 200
    mock_audit.assert_called_once_with(
        "permission_revoke", {"serial": "s1", "package": "com.example.app", "permission": "android.permission.CAMERA"}
    )


def test_permissions_revoke_maps_adb_error(auth_client):
    with patch("routes.battery.adb_permissions.revoke_permission", side_effect=adb_manager.AdbError("bad")):
        res = _post(auth_client, "/api/devices/s1/packages/com.example.app/permissions/revoke", {"permission": "x"})
    assert res.status_code == 400


def test_permissions_routes_require_login(client):
    assert client.get("/api/devices/s1/packages/com.example.app/permissions").status_code == 401
