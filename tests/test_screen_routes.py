import json
from unittest.mock import patch

from adb import manager as adb_manager


def _post(auth_client, url, payload=None):
    return auth_client.post(
        url, data=json.dumps(payload if payload is not None else {}), content_type="application/json",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )


def test_screenshot_success(auth_client):
    with patch("routes.screen.adb_screen.take_screenshot", return_value=b"\x89PNG"):
        res = auth_client.get("/api/devices/s1/screen/screenshot")
    assert res.status_code == 200
    assert res.mimetype == "image/png"
    assert res.data == b"\x89PNG"


def test_screenshot_maps_adb_error(auth_client):
    with patch("routes.screen.adb_screen.take_screenshot", side_effect=adb_manager.AdbError("failed")):
        res = auth_client.get("/api/devices/s1/screen/screenshot")
    assert res.status_code == 400


def test_record_start_success(auth_client):
    with patch("routes.screen.adb_screen.start_recording", return_value={"ok": True, "pid": "1"}), \
         patch("routes.screen.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/screen/record/start", {"time_limit_sec": 60})
    assert res.status_code == 200
    mock_audit.assert_called_once_with("screen_record_start", {"serial": "s1", "time_limit_sec": 60})


def test_record_start_rejects_malformed_time_limit(auth_client):
    res = _post(auth_client, "/api/devices/s1/screen/record/start", {"time_limit_sec": "not-a-number"})
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_time_limit_sec"


def test_record_stop_success(auth_client):
    with patch("routes.screen.adb_screen.stop_recording", return_value={"ok": True, "remote_path": "/x.mp4"}), \
         patch("routes.screen.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/screen/record/stop")
    assert res.status_code == 200
    mock_audit.assert_called_once_with("screen_record_stop", {"serial": "s1"})


def test_record_status_success(auth_client):
    with patch("routes.screen.adb_screen.recording_status", return_value={"active": False, "remote_path": None}):
        res = auth_client.get("/api/devices/s1/screen/record/status")
    assert res.status_code == 200


def test_record_pull_success_cleans_up(auth_client, tmp_path):
    fake_file = tmp_path / "rec.mp4"
    fake_file.write_bytes(b"video-bytes")
    with patch("routes.screen.tempfile.mkdtemp", return_value=str(tmp_path)), \
         patch("routes.screen.adb_files.pull_file", return_value=fake_file), \
         patch("routes.screen.shutil.rmtree") as mock_rmtree:
        res = auth_client.get("/api/devices/s1/screen/record/pull")
        assert res.status_code == 200
        res.close()  # must happen while shutil.rmtree is still patched
        mock_rmtree.assert_called_once_with(str(tmp_path), ignore_errors=True)


def test_record_pull_maps_adb_error(auth_client, tmp_path):
    with patch("routes.screen.tempfile.mkdtemp", return_value=str(tmp_path)), \
         patch("routes.screen.adb_files.pull_file", side_effect=adb_manager.AdbError("no file")), \
         patch("routes.screen.shutil.rmtree") as mock_rmtree:
        res = auth_client.get("/api/devices/s1/screen/record/pull")
    assert res.status_code == 400
    mock_rmtree.assert_called_once_with(str(tmp_path), ignore_errors=True)


def test_rotate_success(auth_client):
    # _simple_action_route() binds each action's backend function into a
    # closure at blueprint-registration (import) time, so patching
    # adb_screen.<fn> here wouldn't reach it -- patch manager.shell instead,
    # same as the equivalent packages-route tests.
    with patch("routes.screen.adb_screen.manager.shell", return_value=("", "", 0)), \
         patch("routes.screen.auth.audit_log"):
        res = _post(auth_client, "/api/devices/s1/screen/rotate", {"degrees": 90})
    assert res.status_code == 200


def test_rotate_rejects_malformed_degrees(auth_client):
    res = _post(auth_client, "/api/devices/s1/screen/rotate", {"degrees": "sideways"})
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_arguments"


def test_auto_rotate_wake_sleep_success(auth_client):
    with patch("routes.screen.adb_screen.manager.shell", return_value=("", "", 0)), \
         patch("routes.screen.auth.audit_log"):
        assert _post(auth_client, "/api/devices/s1/screen/auto-rotate").status_code == 200
        assert _post(auth_client, "/api/devices/s1/screen/wake").status_code == 200
        assert _post(auth_client, "/api/devices/s1/screen/sleep").status_code == 200


def test_brightness_success_and_malformed(auth_client):
    with patch("routes.screen.adb_screen.manager.shell", return_value=("", "", 0)), \
         patch("routes.screen.auth.audit_log"):
        res = _post(auth_client, "/api/devices/s1/screen/brightness", {"level": 128})
    assert res.status_code == 200

    res = _post(auth_client, "/api/devices/s1/screen/brightness", {"level": "bright"})
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_arguments"


def test_action_route_maps_adb_error(auth_client):
    with patch("routes.screen.adb_screen.manager.shell", side_effect=adb_manager.AdbError("bad")):
        res = _post(auth_client, "/api/devices/s1/screen/wake")
    assert res.status_code == 400


def test_action_routes_require_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    res = client.post("/api/devices/s1/screen/wake")
    assert res.status_code == 403
