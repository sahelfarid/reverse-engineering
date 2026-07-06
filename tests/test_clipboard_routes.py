import json
from unittest.mock import patch

from adb import manager as adb_manager


def test_clipboard_get_success(auth_client):
    with patch("routes.battery.adb_clipboard.get_clipboard", return_value={"ok": True, "text": "hello"}):
        res = auth_client.get("/api/devices/s1/clipboard")
    assert res.status_code == 200
    assert res.get_json()["text"] == "hello"


def test_clipboard_get_maps_adb_error(auth_client):
    with patch("routes.battery.adb_clipboard.get_clipboard", side_effect=adb_manager.AdbError("bad")):
        res = auth_client.get("/api/devices/s1/clipboard")
    assert res.status_code == 400


def test_clipboard_set_success_and_audit_log(auth_client):
    with patch("routes.battery.adb_clipboard.set_clipboard", return_value={"ok": True, "note": "sent"}), \
         patch("routes.battery.auth.audit_log") as mock_audit:
        res = auth_client.post(
            "/api/devices/s1/clipboard",
            data=json.dumps({"text": "hello world"}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    mock_audit.assert_called_once_with("clipboard_write", {"serial": "s1", "length": 11})


def test_clipboard_set_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    res = client.post("/api/devices/s1/clipboard")
    assert res.status_code == 403


def test_clipboard_set_maps_adb_error(auth_client):
    with patch("routes.battery.adb_clipboard.set_clipboard", side_effect=adb_manager.AdbError("bad")):
        res = auth_client.post(
            "/api/devices/s1/clipboard",
            data=json.dumps({"text": "x"}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 400


def test_clipboard_history_success(auth_client):
    with patch("routes.battery.adb_clipboard.get_clipboard_history", return_value=["a", "b"]):
        res = auth_client.get("/api/devices/s1/clipboard/history")
    assert res.status_code == 200
    assert res.get_json()["history"] == ["a", "b"]


def test_clipboard_routes_require_login(client):
    assert client.get("/api/devices/s1/clipboard").status_code == 401
    assert client.get("/api/devices/s1/clipboard/history").status_code == 401
