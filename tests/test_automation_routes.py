import json
from unittest.mock import patch

from adb import manager as adb_manager


def _post(auth_client, url, payload=None):
    return auth_client.post(
        url, data=json.dumps(payload if payload is not None else {}), content_type="application/json",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )


def test_tap_success(auth_client):
    with patch("routes.automation.adb_automation.tap", return_value={"ok": True}) as mock_tap:
        res = _post(auth_client, "/api/devices/s1/input/tap", {"x": 10, "y": 20})
    assert res.status_code == 200
    mock_tap.assert_called_once_with("s1", 10, 20)


def test_tap_rejects_malformed_coordinates(auth_client):
    res = _post(auth_client, "/api/devices/s1/input/tap", {"x": "not-a-number", "y": 20})
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_x"


def test_swipe_success(auth_client):
    with patch("routes.automation.adb_automation.swipe", return_value={"ok": True}) as mock_swipe:
        res = _post(auth_client, "/api/devices/s1/input/swipe", {"x1": 1, "y1": 2, "x2": 3, "y2": 4, "duration_ms": 500})
    assert res.status_code == 200
    mock_swipe.assert_called_once_with("s1", 1, 2, 3, 4, 500)


def test_swipe_rejects_malformed_duration(auth_client):
    res = _post(auth_client, "/api/devices/s1/input/swipe", {"duration_ms": "slow"})
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_duration_ms"


def test_long_press_success_and_malformed(auth_client):
    with patch("routes.automation.adb_automation.long_press", return_value={"ok": True}) as mock_lp:
        res = _post(auth_client, "/api/devices/s1/input/long-press", {"x": 1, "y": 2, "duration_ms": 900})
    assert res.status_code == 200
    mock_lp.assert_called_once_with("s1", 1, 2, 900)

    res = _post(auth_client, "/api/devices/s1/input/long-press", {"x": None})
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_x"


def test_text_success_and_audit_log(auth_client):
    with patch("routes.automation.adb_automation.type_text", return_value={"ok": True}), \
         patch("routes.automation.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/input/text", {"text": "hello"})
    assert res.status_code == 200
    mock_audit.assert_called_once_with("input_text", {"serial": "s1", "length": 5})


def test_keyevent_success(auth_client):
    with patch("routes.automation.adb_automation.keyevent", return_value={"ok": True}):
        res = _post(auth_client, "/api/devices/s1/input/keyevent", {"code": "KEYCODE_HOME"})
    assert res.status_code == 200


def test_screen_size_success(auth_client):
    with patch("routes.automation.adb_automation.get_screen_size", return_value={"width": 1080, "height": 1920}):
        res = auth_client.get("/api/devices/s1/screen-size")
    assert res.status_code == 200
    assert res.get_json()["width"] == 1080


def test_screen_size_maps_adb_error(auth_client):
    with patch("routes.automation.adb_automation.get_screen_size", side_effect=adb_manager.AdbError("bad")):
        res = auth_client.get("/api/devices/s1/screen-size")
    assert res.status_code == 400


def test_list_macros_success(auth_client):
    with patch("routes.automation.adb_automation.list_macros", return_value={"m1": []}):
        res = auth_client.get("/api/macros")
    assert res.status_code == 200
    assert res.get_json()["macros"] == {"m1": []}


def test_save_macro_missing_fields(auth_client):
    res = _post(auth_client, "/api/macros", {"name": "", "steps": []})
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_fields"

    res = _post(auth_client, "/api/macros", {"name": "m1", "steps": "not-a-list"})
    assert res.status_code == 400


def test_save_macro_success_and_audit_log(auth_client):
    with patch("routes.automation.adb_automation.save_macro", return_value={"ok": True}), \
         patch("routes.automation.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/macros", {"name": "m1", "steps": [{"type": "tap", "x": 1, "y": 2}]})
    assert res.status_code == 200
    mock_audit.assert_called_once_with("macro_save", {"name": "m1", "steps": 1})


def test_save_macro_maps_adb_error(auth_client):
    with patch("routes.automation.adb_automation.save_macro", side_effect=adb_manager.AdbError("invalid macro name")):
        res = _post(auth_client, "/api/macros", {"name": "m1", "steps": []})
    assert res.status_code == 400


def test_delete_macro_success_and_audit_log(auth_client):
    with patch("routes.automation.adb_automation.delete_macro", return_value={"ok": True}), \
         patch("routes.automation.auth.audit_log") as mock_audit:
        res = auth_client.delete("/api/macros/m1", headers={"X-CSRF-Token": auth_client.csrf_token})
    assert res.status_code == 200
    mock_audit.assert_called_once_with("macro_delete", {"name": "m1"})


def test_play_macro_not_found(auth_client):
    with patch("routes.automation.adb_automation.list_macros", return_value={}):
        res = _post(auth_client, "/api/devices/s1/macros/missing/play")
    assert res.status_code == 404
    assert res.get_json()["error"] == "macro_not_found"


def test_play_macro_success_and_audit_log(auth_client):
    with patch("routes.automation.adb_automation.list_macros", return_value={"m1": [{"type": "tap", "x": 1, "y": 2}]}), \
         patch("routes.automation.adb_automation.play_macro", return_value={"ok": True, "results": []}), \
         patch("routes.automation.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/macros/m1/play")
    assert res.status_code == 200
    mock_audit.assert_called_once_with("macro_play", {"serial": "s1", "name": "m1"})


def test_play_macro_maps_adb_error(auth_client):
    with patch("routes.automation.adb_automation.list_macros", return_value={"m1": []}), \
         patch("routes.automation.adb_automation.play_macro", side_effect=adb_manager.AdbError("bad")):
        res = _post(auth_client, "/api/devices/s1/macros/m1/play")
    assert res.status_code == 400


def test_mutating_routes_require_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    assert client.post("/api/devices/s1/input/tap").status_code == 403
    assert client.post("/api/macros").status_code == 403
