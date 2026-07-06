import json
from unittest.mock import patch

from adb import manager as adb_manager


def test_stream_success_emits_sse_data_lines(auth_client):
    entries = [{"raw": "line1", "level": "I"}, {"raw": "line2", "level": "E"}]
    with patch("routes.logcat.adb_logcat.stream_logcat", return_value=iter(entries)):
        res = auth_client.get("/api/devices/s1/logcat/stream")
        body = res.get_data(as_text=True)
    assert res.status_code == 200
    assert res.mimetype == "text/event-stream"
    assert f"data: {json.dumps(entries[0])}" in body
    assert f"data: {json.dumps(entries[1])}" in body


def test_stream_emits_error_event_on_adb_error(auth_client):
    def raising_generator(*args, **kwargs):
        raise adb_manager.AdbError("invalid regex query: bad")
        yield  # pragma: no cover -- makes this a generator function

    with patch("routes.logcat.adb_logcat.stream_logcat", side_effect=raising_generator):
        res = auth_client.get("/api/devices/s1/logcat/stream?query=(")
        body = res.get_data(as_text=True)
    assert "event: error" in body
    assert "invalid regex query" in body


def test_stream_resolves_pid_from_package(auth_client):
    with patch("routes.logcat.adb_logcat.resolve_pid", return_value="4321") as mock_resolve, \
         patch("routes.logcat.adb_logcat.stream_logcat", return_value=iter([])) as mock_stream:
        auth_client.get("/api/devices/s1/logcat/stream?package=com.example.app").get_data()
    mock_resolve.assert_called_once_with("s1", "com.example.app")
    assert mock_stream.call_args[0][2] == "4321"  # pid positional arg


def test_stream_requires_login(client):
    assert client.get("/api/devices/s1/logcat/stream").status_code == 401


def test_clear_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    res = client.post("/api/devices/s1/logcat/clear")
    assert res.status_code == 403


def test_clear_success_and_audit_log(auth_client):
    with patch("routes.logcat.adb_logcat.clear_logcat", return_value={"ok": True}), \
         patch("routes.logcat.auth.audit_log") as mock_audit:
        res = auth_client.post("/api/devices/s1/logcat/clear", headers={"X-CSRF-Token": auth_client.csrf_token})
    assert res.status_code == 200
    mock_audit.assert_called_once_with("logcat_clear", {"serial": "s1"})


def test_clear_maps_adb_not_installed(auth_client):
    with patch("routes.logcat.adb_logcat.clear_logcat", side_effect=adb_manager.AdbNotInstalledError("x")):
        res = auth_client.post("/api/devices/s1/logcat/clear", headers={"X-CSRF-Token": auth_client.csrf_token})
    assert res.status_code == 503
