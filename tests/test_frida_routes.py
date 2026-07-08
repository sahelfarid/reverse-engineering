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


def test_system_parameters_success(auth_client):
    system = {"os": {"id": "android"}, "arch": "arm64"}
    with patch("routes.frida.frida_manager.get_system_parameters", return_value=system):
        res = auth_client.get("/api/devices/s1/frida/system")
    assert res.status_code == 200
    assert res.get_json()["system"] == system


def test_system_parameters_maps_adb_error(auth_client):
    with patch("routes.frida.frida_manager.get_system_parameters",
               side_effect=adb_manager.AdbError("failed to query system parameters")):
        res = auth_client.get("/api/devices/s1/frida/system")
    assert res.status_code == 400


def test_process_details_success(auth_client):
    proc = {"pid": 42, "name": "com.example", "parameters": {"path": "/x"}}
    with patch("routes.frida.frida_manager.get_process", return_value=proc) as mock_get:
        res = auth_client.get("/api/devices/s1/frida/process?q=com.example")
    assert res.status_code == 200
    assert res.get_json()["process"] == proc
    mock_get.assert_called_once_with("s1", "com.example")


def test_process_details_maps_adb_error(auth_client):
    with patch("routes.frida.frida_manager.get_process",
               side_effect=adb_manager.AdbError("process lookup failed")):
        res = auth_client.get("/api/devices/s1/frida/process?q=nope")
    assert res.status_code == 400


def test_enable_spawn_gating_success_and_audit_log(auth_client):
    with patch("routes.frida.frida_manager.enable_spawn_gating", return_value={"ok": True, "spawn_gating": True}), \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/frida/spawn-gating/enable")
    assert res.status_code == 200
    mock_audit.assert_called_once_with("frida_spawn_gating_enable", {"serial": "s1"})


def test_disable_spawn_gating_success(auth_client):
    with patch("routes.frida.frida_manager.disable_spawn_gating", return_value={"ok": True, "spawn_gating": False}), \
         patch("routes.frida.auth.audit_log"):
        res = _post(auth_client, "/api/devices/s1/frida/spawn-gating/disable")
    assert res.status_code == 200
    assert res.get_json()["spawn_gating"] is False


def test_pending_spawn_success(auth_client):
    pending = [{"pid": 10, "identifier": "com.a"}]
    with patch("routes.frida.frida_manager.list_pending_spawn", return_value=pending):
        res = auth_client.get("/api/devices/s1/frida/pending-spawn")
    assert res.status_code == 200
    assert res.get_json()["pending"] == pending


def test_pending_children_success(auth_client):
    pending = [{"pid": 10, "parent_pid": 5, "identifier": "com.a", "path": "/a"}]
    with patch("routes.frida.frida_manager.list_pending_children", return_value=pending):
        res = auth_client.get("/api/devices/s1/frida/pending-children")
    assert res.status_code == 200
    assert res.get_json()["pending"] == pending


def test_enable_child_gating_success_and_audit_log(auth_client):
    with patch("routes.frida.frida_manager.set_child_gating", return_value={"ok": True, "child_gating": True}) as mock_set, \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/frida/sessions/sess-1/child-gating/enable")
    assert res.status_code == 200
    mock_set.assert_called_once_with("sess-1", True)
    mock_audit.assert_called_once_with("frida_child_gating_enable", {"session_id": "sess-1"})


def test_disable_child_gating_success(auth_client):
    with patch("routes.frida.frida_manager.set_child_gating", return_value={"ok": True, "child_gating": False}) as mock_set, \
         patch("routes.frida.auth.audit_log"):
        res = _post(auth_client, "/api/frida/sessions/sess-1/child-gating/disable")
    assert res.status_code == 200
    mock_set.assert_called_once_with("sess-1", False)
    assert res.get_json()["child_gating"] is False


def test_child_gating_maps_adb_error(auth_client):
    with patch("routes.frida.frida_manager.set_child_gating",
               side_effect=adb_manager.AdbError("session is detached")):
        res = _post(auth_client, "/api/frida/sessions/sess-1/child-gating/enable")
    assert res.status_code == 400


def test_child_gating_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    res = client.post("/api/frida/sessions/sess-1/child-gating/enable")
    assert res.status_code == 403


def test_resume_pid_success_and_audit_log(auth_client):
    with patch("routes.frida.frida_manager.resume_pid", return_value={"ok": True, "pid": 1234, "resumed": True}), \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/frida/resume/1234")
    assert res.status_code == 200
    mock_audit.assert_called_once_with("frida_resume", {"serial": "s1", "pid": 1234})


def test_kill_pid_success_and_audit_log(auth_client):
    with patch("routes.frida.frida_manager.kill_pid", return_value={"ok": True, "pid": 55, "killed": True}), \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/frida/kill/55")
    assert res.status_code == 200
    mock_audit.assert_called_once_with("frida_kill", {"serial": "s1", "pid": 55})


def test_kill_pid_maps_adb_error(auth_client):
    with patch("routes.frida.frida_manager.kill_pid", side_effect=adb_manager.AdbError("failed to kill pid 55")):
        res = _post(auth_client, "/api/devices/s1/frida/kill/55")
    assert res.status_code == 400


def test_kill_by_name_success_and_audit_log(auth_client):
    with patch("routes.frida.frida_manager.kill_process",
               return_value={"ok": True, "name": "com.example", "killed": True}) as mock_kill, \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/frida/kill", {"target": "com.example"})
    assert res.status_code == 200
    mock_kill.assert_called_once_with("s1", "com.example")
    mock_audit.assert_called_once_with("frida_kill", {"serial": "s1", "target": "com.example"})


def test_kill_by_name_missing_target(auth_client):
    res = _post(auth_client, "/api/devices/s1/frida/kill", {})
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_target"


def test_spawn_gating_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    res = client.post("/api/devices/s1/frida/spawn-gating/enable")
    assert res.status_code == 403


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
    mock_attach.assert_called_once_with("s1", "1234", "console.log(1);", None, None)
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
    mock_attach.assert_called_once_with("s1", {"spawn": "com.example.app"}, "console.log(2);", None, None)


def test_attach_passes_runtime(auth_client):
    with patch("routes.frida.frida_manager.attach", return_value="sess-v8") as mock_attach, \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/frida/attach", {
            "script_source": "console.log(3);", "target": "42", "runtime": "v8",
        })
    assert res.status_code == 200
    mock_attach.assert_called_once_with("s1", "42", "console.log(3);", "v8", None)
    assert mock_audit.call_args[0][1]["runtime"] == "v8"


def test_attach_passes_params(auth_client):
    with patch("routes.frida.frida_manager.attach", return_value="sess-p") as mock_attach, \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/frida/attach", {
            "script_source": "console.log(PARAMS.className);",
            "target": "7",
            "params": {"className": "com.example.App"},
        })
    assert res.status_code == 200
    mock_attach.assert_called_once_with(
        "s1", "7", "console.log(PARAMS.className);", None, {"className": "com.example.App"},
    )
    assert mock_audit.call_args[0][1]["has_params"] is True


def test_attach_rejects_non_object_params(auth_client):
    res = _post(auth_client, "/api/devices/s1/frida/attach", {
        "script_source": "x", "target": "1", "params": ["not", "an", "object"],
    })
    assert res.status_code == 400
    assert res.get_json()["error"] == "params must be a JSON object"


def test_attach_maps_adb_error(auth_client):
    with patch("routes.frida.frida_manager.attach", side_effect=adb_manager.AdbError("attach failed")):
        res = _post(auth_client, "/api/devices/s1/frida/attach", {"script_source": "x", "target": "1"})
    assert res.status_code == 400


def test_sessions_list_success(auth_client):
    with patch("routes.frida.frida_manager.list_sessions", return_value=[{"id": "sess-1"}]):
        res = auth_client.get("/api/frida/sessions")
    assert res.status_code == 200


def test_get_session_success(auth_client):
    with patch("routes.frida.frida_manager.get_session",
               return_value={"id": "sess-1", "detached": False}):
        res = auth_client.get("/api/frida/sessions/sess-1")
    assert res.status_code == 200
    assert res.get_json()["session"]["id"] == "sess-1"


def test_get_session_maps_not_found(auth_client):
    with patch("routes.frida.frida_manager.get_session",
               side_effect=adb_manager.AdbError("session not found")):
        res = auth_client.get("/api/frida/sessions/missing")
    assert res.status_code == 400


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


def test_list_exports_success(auth_client):
    with patch("routes.frida.frida_manager.list_script_exports", return_value=["foo", "bar"]):
        res = auth_client.get("/api/frida/sessions/sess-1/exports")
    assert res.status_code == 200
    assert res.get_json()["exports"] == ["foo", "bar"]


def test_call_export_success_and_audit_log(auth_client):
    with patch("routes.frida.frida_manager.call_script_export", return_value={"x": 1}) as mock_call, \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/frida/sessions/sess-1/exports/get_data", {"args": [1, 2]})
    assert res.status_code == 200
    assert res.get_json()["result"] == {"x": 1}
    mock_call.assert_called_once_with("sess-1", "get_data", [1, 2])
    mock_audit.assert_called_once_with("frida_export_call", {"session_id": "sess-1", "export": "get_data"})


def test_call_export_maps_adb_error(auth_client):
    with patch("routes.frida.frida_manager.call_script_export",
               side_effect=adb_manager.AdbError("export 'x' not found")):
        res = _post(auth_client, "/api/frida/sessions/sess-1/exports/x", {"args": []})
    assert res.status_code == 400


def test_call_export_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    res = client.post("/api/frida/sessions/sess-1/exports/foo")
    assert res.status_code == 403


def test_post_message_success_and_audit_log(auth_client):
    with patch("routes.frida.frida_manager.post_message", return_value={"ok": True}) as mock_post, \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/frida/sessions/sess-1/post", {"message": {"cmd": "ping"}})
    assert res.status_code == 200
    mock_post.assert_called_once_with("sess-1", {"cmd": "ping"}, None)
    mock_audit.assert_called_once_with("frida_post_message", {"session_id": "sess-1", "has_data": False})


def test_post_message_allows_data_only(auth_client):
    with patch("routes.frida.frida_manager.post_message", return_value={"ok": True}) as mock_post, \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/frida/sessions/sess-1/post", {"data": "deadbeef"})
    assert res.status_code == 200
    mock_post.assert_called_once_with("sess-1", None, "deadbeef")
    assert mock_audit.call_args[0][1]["has_data"] is True


def test_post_message_missing_message_and_data(auth_client):
    res = _post(auth_client, "/api/frida/sessions/sess-1/post", {})
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_message_or_data"


def test_post_message_maps_adb_error(auth_client):
    with patch("routes.frida.frida_manager.post_message",
               side_effect=adb_manager.AdbError("session is detached")):
        res = _post(auth_client, "/api/frida/sessions/sess-1/post", {"message": {}})
    assert res.status_code == 400


def test_eternalize_success_and_audit_log(auth_client):
    with patch("routes.frida.frida_manager.eternalize_session", return_value={"ok": True, "eternalized": True}), \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/frida/sessions/sess-1/eternalize", {})
    assert res.status_code == 200
    assert res.get_json()["eternalized"] is True
    mock_audit.assert_called_once_with("frida_eternalize", {"session_id": "sess-1"})


def test_interrupt_script_success_and_audit_log(auth_client):
    with patch("routes.frida.frida_manager.interrupt_script", return_value={"ok": True, "interrupted": True}), \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/frida/sessions/sess-1/interrupt")
    assert res.status_code == 200
    mock_audit.assert_called_once_with("frida_interrupt", {"session_id": "sess-1"})


def test_terminate_script_success_and_audit_log(auth_client):
    with patch("routes.frida.frida_manager.terminate_script", return_value={"ok": True, "terminated": True}), \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/frida/sessions/sess-1/terminate")
    assert res.status_code == 200
    mock_audit.assert_called_once_with("frida_terminate", {"session_id": "sess-1"})


def test_terminate_script_maps_adb_error(auth_client):
    with patch("routes.frida.frida_manager.terminate_script",
               side_effect=adb_manager.AdbError("session is detached")):
        res = _post(auth_client, "/api/frida/sessions/sess-1/terminate")
    assert res.status_code == 400


def test_interrupt_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    res = client.post("/api/frida/sessions/sess-1/interrupt")
    assert res.status_code == 403


def test_attach_passes_spawn_options(auth_client):
    with patch("routes.frida.frida_manager.attach", return_value="sess-spawn") as mock_attach, \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/frida/attach", {
            "script_source": "console.log(1);",
            "spawn": "com.example",
            "argv": ["--debug"],
            "env": {"A": "1"},
            "cwd": "/data/local/tmp",
            "stdio": "pipe",
        })
    assert res.status_code == 200
    target = mock_attach.call_args[0][1]
    assert target == {
        "spawn": "com.example",
        "argv": ["--debug"],
        "env": {"A": "1"},
        "cwd": "/data/local/tmp",
        "stdio": "pipe",
    }
    assert mock_audit.call_args[0][1]["has_spawn_options"] is True


def test_input_to_process_utf8_and_audit(auth_client):
    with patch("routes.frida.frida_manager.input_to_process",
               return_value={"ok": True, "pid": 5, "bytes": 3}) as mock_in, \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/frida/input/5", {"data": "abc"})
    assert res.status_code == 200
    mock_in.assert_called_once_with("s1", 5, "abc")
    mock_audit.assert_called_once_with("frida_input", {"serial": "s1", "pid": 5, "bytes": 3})


def test_input_to_process_hex_encoding(auth_client):
    with patch("routes.frida.frida_manager.input_to_process",
               return_value={"ok": True, "pid": 5, "bytes": 2}) as mock_in, \
         patch("routes.frida.auth.audit_log"):
        res = _post(auth_client, "/api/devices/s1/frida/input/5", {"data": "6869", "encoding": "hex"})
    assert res.status_code == 200
    mock_in.assert_called_once_with("s1", 5, b"hi")


def test_input_to_process_missing_data(auth_client):
    res = _post(auth_client, "/api/devices/s1/frida/input/5", {})
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_data"


def test_device_events_success(auth_client):
    events = [{"type": "spawn-added", "pid": 1, "ts": 1.0}]
    with patch("routes.frida.frida_manager.list_device_events", return_value=events) as mock_list:
        res = auth_client.get("/api/devices/s1/frida/events?after=0.5&limit=10")
    assert res.status_code == 200
    assert res.get_json()["events"] == events
    mock_list.assert_called_once_with("s1", 0.5, "10")


def test_wire_device_events_success(auth_client):
    with patch("routes.frida.frida_manager.wire_device_events",
               return_value={"ok": True, "wired": True, "already": False}), \
         patch("routes.frida.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/frida/events/wire")
    assert res.status_code == 200
    mock_audit.assert_called_once_with("frida_events_wire", {"serial": "s1"})


def test_export_session_json(auth_client):
    payload = {"ok": True, "format": "json", "messages": [], "count": 0, "session_id": "sess-1"}
    with patch("routes.frida.frida_manager.export_session_messages", return_value=payload):
        res = auth_client.get("/api/frida/sessions/sess-1/export?format=json")
    assert res.status_code == 200
    assert res.get_json()["format"] == "json"


def test_export_session_text_attachment(auth_client):
    payload = {
        "ok": True, "format": "text", "text": "info: hi\n", "count": 1, "session_id": "sess-1",
    }
    with patch("routes.frida.frida_manager.export_session_messages", return_value=payload):
        res = auth_client.get("/api/frida/sessions/sess-1/export?format=text")
    assert res.status_code == 200
    assert res.mimetype.startswith("text/plain")
    assert b"info: hi" in res.data
    assert "frida-session-sess-1.txt" in res.headers.get("Content-Disposition", "")


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
