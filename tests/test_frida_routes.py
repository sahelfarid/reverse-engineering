import json
from unittest.mock import patch

from adb import manager as adb_manager


def _post(auth_client, url, payload=None):
    return auth_client.post(
        url, data=json.dumps(payload if payload is not None else {}), content_type="application/json",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )


def test_status_success(auth_client):
    with patch("routes.frida.frida_manager.get_status", return_value={"ok": True, "devices": []}):
        res = auth_client.get("/api/frida/status")
    assert res.status_code == 200


def test_push_server_success_and_audit_log(auth_client):
    with patch("routes.frida.frida_manager.push_server", return_value={"ok": True, "remote_path": "x"}), \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/frida/server/push")
    assert res.status_code == 200
    mock_audit.assert_called_once_with("frida_server_push", {"serial": "s1"})


def test_push_server_maps_adb_error(auth_client):
    with patch("routes.frida.frida_manager.push_server", side_effect=adb_manager.AdbError("must be rooted")):
        res = _post(auth_client, "/api/devices/s1/frida/server/push")
    assert res.status_code == 400


def test_push_server_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    res = client.post("/api/devices/s1/frida/server/push")
    assert res.status_code == 403


def test_start_server_success_and_audit_log(auth_client):
    with patch("routes.frida.frida_manager.start_server", return_value={"ok": True, "pid": "123"}), \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/frida/server/start")
    assert res.status_code == 200
    mock_audit.assert_called_once_with("frida_server_start", {"serial": "s1", "pid": "123"})


def test_stop_server_success_and_audit_log(auth_client):
    with patch("routes.frida.frida_manager.stop_server", return_value={"ok": True, "stopped": True, "pid": "123"}), \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/frida/server/stop")
    assert res.status_code == 200
    mock_audit.assert_called_once_with("frida_server_stop", {"serial": "s1", "pid": "123"})


def test_list_processes_success(auth_client):
    with patch("routes.frida.frida_manager.list_processes", return_value=[{"pid": 1, "name": "init"}]):
        res = auth_client.get("/api/devices/s1/frida/processes")
    assert res.status_code == 200
    assert res.get_json()["processes"] == [{"pid": 1, "name": "init"}]


def test_list_applications_success(auth_client):
    apps = [{"identifier": "com.a", "name": "Alpha", "pid": 1, "running": True}]
    with patch("routes.frida.frida_manager.list_applications", return_value=apps):
        res = auth_client.get("/api/devices/s1/frida/applications")
    assert res.status_code == 200
    assert res.get_json()["applications"] == apps


def test_list_applications_maps_adb_error(auth_client):
    with patch("routes.frida.frida_manager.list_applications",
               side_effect=adb_manager.AdbError("failed to enumerate applications")):
        res = auth_client.get("/api/devices/s1/frida/applications")
    assert res.status_code == 400


def test_frontmost_application_success(auth_client):
    app = {"identifier": "com.a", "name": "Alpha", "pid": 1, "running": True}
    with patch("routes.frida.frida_manager.get_frontmost_application", return_value=app):
        res = auth_client.get("/api/devices/s1/frida/frontmost")
    assert res.status_code == 200
    assert res.get_json()["application"] == app


def test_attach_missing_script_source(auth_client):
    res = _post(auth_client, "/api/devices/s1/frida/attach", {"target": "1234"})
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_script_source"


def test_attach_unknown_script_name(auth_client):
    with patch("routes.frida.frida_manager.list_scripts", return_value={}):
        res = _post(auth_client, "/api/devices/s1/frida/attach", {"script_name": "does-not-exist"})
    assert res.status_code == 404
    assert res.get_json()["error"] == "script_not_found"


def test_attach_with_script_name_resolves_source_and_audit_logs(auth_client):
    with patch("routes.frida.frida_manager.list_scripts", return_value={"demo": {"source": "console.log(1);"}}), \
         patch("routes.frida.frida_manager.attach", return_value="sess-1") as mock_attach, \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/frida/attach", {"script_name": "demo", "target": "1234"})
    assert res.status_code == 200
    assert res.get_json()["session_id"] == "sess-1"
    mock_attach.assert_called_once_with("s1", "1234", "console.log(1);")
    audit_details = mock_audit.call_args[0][1]
    assert audit_details["script_name"] == "demo"
    assert "script_sha256" in audit_details
    assert "source" not in audit_details  # full script source must never be audit-logged


def test_attach_with_inline_source_and_spawn_target(auth_client):
    with patch("routes.frida.frida_manager.attach", return_value="sess-2") as mock_attach, \
         patch("routes.frida.auth.audit_log"):
        res = _post(auth_client, "/api/devices/s1/frida/attach", {
            "script_source": "console.log(2);", "spawn": "com.example.app",
        })
    assert res.status_code == 200
    mock_attach.assert_called_once_with("s1", {"spawn": "com.example.app"}, "console.log(2);")


def test_attach_maps_adb_error(auth_client):
    with patch("routes.frida.frida_manager.attach", side_effect=adb_manager.AdbError("attach failed")):
        res = _post(auth_client, "/api/devices/s1/frida/attach", {"script_source": "x", "target": "1"})
    assert res.status_code == 400


def test_sessions_list_success(auth_client):
    with patch("routes.frida.frida_manager.list_sessions", return_value=[{"id": "sess-1"}]):
        res = auth_client.get("/api/frida/sessions")
    assert res.status_code == 200


def test_stream_emits_sse_data(auth_client):
    entries = [{"message": {"type": "send", "payload": "hi"}}]
    with patch("routes.frida.frida_manager.stream_messages", return_value=iter(entries)):
        res = auth_client.get("/api/frida/sessions/sess-1/stream")
        body = res.get_data(as_text=True)
    assert res.status_code == 200
    assert res.mimetype == "text/event-stream"
    assert json.dumps(entries[0]) in body


def test_stream_emits_error_event_for_unknown_session(auth_client):
    def raising_generator(*args, **kwargs):
        raise adb_manager.AdbError("session not found")
        yield  # pragma: no cover -- makes this a generator function

    with patch("routes.frida.frida_manager.stream_messages", side_effect=raising_generator):
        res = auth_client.get("/api/frida/sessions/does-not-exist/stream")
        body = res.get_data(as_text=True)
    assert "event: error" in body
    assert "session not found" in body


def test_detach_success_and_audit_log(auth_client):
    with patch("routes.frida.frida_manager.detach", return_value={"ok": True, "detached": True}), \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/frida/sessions/sess-1/detach")
    assert res.status_code == 200
    mock_audit.assert_called_once_with("frida_detach", {"session_id": "sess-1"})


def test_list_scripts_success(auth_client):
    with patch("routes.frida.frida_manager.list_scripts", return_value={"demo": {"readonly": False}}):
        res = auth_client.get("/api/frida/scripts")
    assert res.status_code == 200


def test_save_script_success_and_audit_log_excludes_source(auth_client):
    with patch("routes.frida.frida_manager.save_script", return_value={"ok": True, "name": "demo"}), \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/frida/scripts", {"name": "demo", "source": "console.log('secret');"})
    assert res.status_code == 200
    audit_details = mock_audit.call_args[0][1]
    assert audit_details["name"] == "demo"
    assert "source" not in audit_details
    assert "script_sha256" in audit_details


def test_save_script_maps_adb_error(auth_client):
    with patch("routes.frida.frida_manager.save_script", side_effect=adb_manager.AdbError("invalid script name")):
        res = _post(auth_client, "/api/frida/scripts", {"name": "../escape", "source": "x"})
    assert res.status_code == 400


def test_delete_script_success_and_audit_log(auth_client):
    with patch("routes.frida.frida_manager.delete_script", return_value={"ok": True}), \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = auth_client.delete("/api/frida/scripts/demo", headers={"X-CSRF-Token": auth_client.csrf_token})
    assert res.status_code == 200
    mock_audit.assert_called_once_with("frida_script_delete", {"name": "demo"})


def test_delete_script_maps_adb_error(auth_client):
    with patch("routes.frida.frida_manager.delete_script", side_effect=adb_manager.AdbError("default scripts are read-only")):
        res = auth_client.delete("/api/frida/scripts/template-method-tracer", headers={"X-CSRF-Token": auth_client.csrf_token})
    assert res.status_code == 400


def test_frida_routes_require_login(client):
    assert client.get("/api/frida/status").status_code == 401
    assert client.get("/api/frida/scripts").status_code == 401
    assert client.get("/api/frida/sessions").status_code == 401
