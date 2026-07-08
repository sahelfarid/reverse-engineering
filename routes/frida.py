import json

from flask import Blueprint, Response, jsonify, request, stream_with_context

import auth
from adb import frida_manager
from adb import manager as adb_manager

bp = Blueprint("frida", __name__)


def _wrap(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except adb_manager.AdbNotInstalledError:
        return None, (jsonify({"ok": False, "error": "adb_not_installed"}), 503)
    except adb_manager.AdbError as exc:
        return None, (jsonify({"ok": False, "error": str(exc)}), 400)


@bp.get("/api/frida/status")
@auth.login_required
def status():
    return jsonify(frida_manager.get_status())


@bp.post("/api/devices/<serial>/frida/server/push")
@auth.login_required
@auth.csrf_protect
def push_server(serial):
    result, err = _wrap(frida_manager.push_server, serial)
    if err:
        return err
    auth.audit_log("frida_server_push", {"serial": serial})
    return jsonify(result)


@bp.post("/api/devices/<serial>/frida/server/start")
@auth.login_required
@auth.csrf_protect
def start_server(serial):
    result, err = _wrap(frida_manager.start_server, serial)
    if err:
        return err
    auth.audit_log("frida_server_start", {"serial": serial, "pid": result.get("pid")})
    return jsonify(result)


@bp.post("/api/devices/<serial>/frida/server/stop")
@auth.login_required
@auth.csrf_protect
def stop_server(serial):
    result, err = _wrap(frida_manager.stop_server, serial)
    if err:
        return err
    auth.audit_log("frida_server_stop", {"serial": serial, "pid": result.get("pid")})
    return jsonify(result)


@bp.get("/api/devices/<serial>/frida/processes")
@auth.login_required
def list_processes(serial):
    result, err = _wrap(frida_manager.list_processes, serial)
    return err or jsonify({"ok": True, "processes": result})


@bp.get("/api/devices/<serial>/frida/applications")
@auth.login_required
def list_applications(serial):
    result, err = _wrap(frida_manager.list_applications, serial)
    return err or jsonify({"ok": True, "applications": result})


@bp.get("/api/devices/<serial>/frida/frontmost")
@auth.login_required
def frontmost_application(serial):
    result, err = _wrap(frida_manager.get_frontmost_application, serial)
    return err or jsonify({"ok": True, "application": result})


@bp.get("/api/devices/<serial>/frida/system")
@auth.login_required
def system_parameters(serial):
    result, err = _wrap(frida_manager.get_system_parameters, serial)
    return err or jsonify({"ok": True, "system": result})


@bp.get("/api/devices/<serial>/frida/process")
@auth.login_required
def process_details(serial):
    result, err = _wrap(frida_manager.get_process, serial, request.args.get("q", ""))
    return err or jsonify({"ok": True, "process": result})


@bp.post("/api/devices/<serial>/frida/spawn-gating/enable")
@auth.login_required
@auth.csrf_protect
def enable_spawn_gating(serial):
    result, err = _wrap(frida_manager.enable_spawn_gating, serial)
    if err:
        return err
    auth.audit_log("frida_spawn_gating_enable", {"serial": serial})
    return jsonify(result)


@bp.post("/api/devices/<serial>/frida/spawn-gating/disable")
@auth.login_required
@auth.csrf_protect
def disable_spawn_gating(serial):
    result, err = _wrap(frida_manager.disable_spawn_gating, serial)
    if err:
        return err
    auth.audit_log("frida_spawn_gating_disable", {"serial": serial})
    return jsonify(result)


@bp.get("/api/devices/<serial>/frida/pending-spawn")
@auth.login_required
def pending_spawn(serial):
    result, err = _wrap(frida_manager.list_pending_spawn, serial)
    return err or jsonify({"ok": True, "pending": result})


@bp.get("/api/devices/<serial>/frida/pending-children")
@auth.login_required
def pending_children(serial):
    result, err = _wrap(frida_manager.list_pending_children, serial)
    return err or jsonify({"ok": True, "pending": result})


@bp.post("/api/devices/<serial>/frida/resume/<int:pid>")
@auth.login_required
@auth.csrf_protect
def resume_pid(serial, pid):
    result, err = _wrap(frida_manager.resume_pid, serial, pid)
    if err:
        return err
    auth.audit_log("frida_resume", {"serial": serial, "pid": pid})
    return jsonify(result)


@bp.post("/api/devices/<serial>/frida/kill/<int:pid>")
@auth.login_required
@auth.csrf_protect
def kill_pid(serial, pid):
    result, err = _wrap(frida_manager.kill_pid, serial, pid)
    if err:
        return err
    auth.audit_log("frida_kill", {"serial": serial, "pid": pid})
    return jsonify(result)


@bp.post("/api/devices/<serial>/frida/input/<int:pid>")
@auth.login_required
@auth.csrf_protect
def input_to_process(serial, pid):
    """Feed bytes to a spawned process's stdin (device.input)."""
    d = request.get_json(silent=True) or {}
    if "data" not in d:
        return jsonify({"ok": False, "error": "missing_data"}), 400
    encoding = str(d.get("encoding") or "utf8").strip().lower()
    raw = d.get("data")
    if encoding == "hex":
        try:
            data = bytes.fromhex(str(raw))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "data must be a hex string"}), 400
    else:
        data = raw if isinstance(raw, (bytes, bytearray)) else str(raw)
    result, err = _wrap(frida_manager.input_to_process, serial, pid, data)
    if err:
        return err
    auth.audit_log("frida_input", {"serial": serial, "pid": pid, "bytes": result.get("bytes")})
    return jsonify(result)


@bp.get("/api/devices/<serial>/frida/events")
@auth.login_required
def device_events(serial):
    """Recent spawn/child/crash/output device events (after_ts for incremental poll)."""
    after = request.args.get("after")
    after_ts = None
    if after not in (None, ""):
        try:
            after_ts = float(after)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "after must be a number (unix timestamp)"}), 400
    limit = request.args.get("limit", 100)
    result, err = _wrap(frida_manager.list_device_events, serial, after_ts, limit)
    return err or jsonify({"ok": True, "events": result})


@bp.post("/api/devices/<serial>/frida/events/wire")
@auth.login_required
@auth.csrf_protect
def wire_device_events(serial):
    result, err = _wrap(frida_manager.wire_device_events, serial)
    if err:
        return err
    auth.audit_log("frida_events_wire", {"serial": serial})
    return jsonify(result)


@bp.post("/api/devices/<serial>/frida/attach")
@auth.login_required
@auth.csrf_protect
def attach(serial):
    d = request.get_json(silent=True) or {}
    source = d.get("script_source")
    script_name = d.get("script_name")
    if script_name and not source:
        scripts = frida_manager.list_scripts()
        if script_name not in scripts:
            return jsonify({"ok": False, "error": "script_not_found"}), 404
        source = scripts[script_name]["source"]
    if not source:
        return jsonify({"ok": False, "error": "missing_script_source"}), 400
    target = d.get("target")
    if d.get("spawn"):
        target = {"spawn": d.get("spawn")}
        opts = d.get("spawn_options") if isinstance(d.get("spawn_options"), dict) else {}
        for key in ("argv", "env", "envp", "cwd", "stdio"):
            if key in d:
                target[key] = d[key]
            elif key in opts:
                target[key] = opts[key]
    runtime = d.get("runtime")
    params = d.get("params")
    if params is not None and not isinstance(params, dict):
        return jsonify({"ok": False, "error": "params must be a JSON object"}), 400
    session_id, err = _wrap(frida_manager.attach, serial, target, source, runtime, params)
    if err:
        return err
    auth.audit_log("frida_attach", {
        "serial": serial,
        "target": target,
        "script_name": script_name,
        "script_sha256": frida_manager.script_hash(source),
        "runtime": runtime,
        "has_params": bool(params),
        "has_spawn_options": bool(
            isinstance(target, dict) and any(k in target for k in ("argv", "env", "envp", "cwd", "stdio"))
        ),
    })
    return jsonify({"ok": True, "session_id": session_id})


@bp.get("/api/frida/sessions")
@auth.login_required
def sessions():
    return jsonify({"ok": True, "sessions": frida_manager.list_sessions()})


@bp.get("/api/frida/sessions/<session_id>")
@auth.login_required
def get_session(session_id):
    result, err = _wrap(frida_manager.get_session, session_id)
    return err or jsonify({"ok": True, "session": result})


@bp.get("/api/frida/sessions/<session_id>/stream")
@auth.login_required
def stream(session_id):
    def generate():
        try:
            for entry in frida_manager.stream_messages(session_id):
                yield f"data: {json.dumps(entry)}\n\n"
        except adb_manager.AdbError as exc:
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@bp.get("/api/frida/sessions/<session_id>/exports")
@auth.login_required
def list_exports(session_id):
    result, err = _wrap(frida_manager.list_script_exports, session_id)
    return err or jsonify({"ok": True, "exports": result})


@bp.post("/api/frida/sessions/<session_id>/exports/<name>")
@auth.login_required
@auth.csrf_protect
def call_export(session_id, name):
    d = request.get_json(silent=True) or {}
    args = d.get("args", [])
    result, err = _wrap(frida_manager.call_script_export, session_id, name, args)
    if err:
        return err
    auth.audit_log("frida_export_call", {"session_id": session_id, "export": name})
    return jsonify({"ok": True, "result": result})


@bp.post("/api/frida/sessions/<session_id>/post")
@auth.login_required
@auth.csrf_protect
def post_message(session_id):
    d = request.get_json(silent=True) or {}
    if "message" not in d:
        return jsonify({"ok": False, "error": "missing_message"}), 400
    result, err = _wrap(frida_manager.post_message, session_id, d.get("message"), d.get("data"))
    if err:
        return err
    auth.audit_log("frida_post_message", {"session_id": session_id})
    return jsonify(result)


@bp.post("/api/frida/sessions/<session_id>/child-gating/enable")
@auth.login_required
@auth.csrf_protect
def enable_child_gating(session_id):
    result, err = _wrap(frida_manager.set_child_gating, session_id, True)
    if err:
        return err
    auth.audit_log("frida_child_gating_enable", {"session_id": session_id})
    return jsonify(result)


@bp.post("/api/frida/sessions/<session_id>/child-gating/disable")
@auth.login_required
@auth.csrf_protect
def disable_child_gating(session_id):
    result, err = _wrap(frida_manager.set_child_gating, session_id, False)
    if err:
        return err
    auth.audit_log("frida_child_gating_disable", {"session_id": session_id})
    return jsonify(result)


@bp.post("/api/frida/sessions/<session_id>/eternalize")
@auth.login_required
@auth.csrf_protect
def eternalize(session_id):
    result, err = _wrap(frida_manager.eternalize_session, session_id)
    if err:
        return err
    auth.audit_log("frida_eternalize", {"session_id": session_id})
    return jsonify(result)


@bp.post("/api/frida/sessions/<session_id>/interrupt")
@auth.login_required
@auth.csrf_protect
def interrupt(session_id):
    result, err = _wrap(frida_manager.interrupt_script, session_id)
    if err:
        return err
    auth.audit_log("frida_interrupt", {"session_id": session_id})
    return jsonify(result)


@bp.post("/api/frida/sessions/<session_id>/terminate")
@auth.login_required
@auth.csrf_protect
def terminate(session_id):
    result, err = _wrap(frida_manager.terminate_script, session_id)
    if err:
        return err
    auth.audit_log("frida_terminate", {"session_id": session_id})
    return jsonify(result)


@bp.post("/api/frida/sessions/<session_id>/detach")
@auth.login_required
@auth.csrf_protect
def detach(session_id):
    result, err = _wrap(frida_manager.detach, session_id)
    if err:
        return err
    auth.audit_log("frida_detach", {"session_id": session_id})
    return jsonify(result)


@bp.get("/api/frida/sessions/<session_id>/export")
@auth.login_required
def export_session(session_id):
    """Download buffered session console output as JSON or plain text."""
    fmt = request.args.get("format", "json")
    result, err = _wrap(frida_manager.export_session_messages, session_id, fmt)
    if err:
        return err
    if result.get("format") == "text":
        text = result.get("text") or ""
        return Response(
            text,
            mimetype="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="frida-session-{session_id}.txt"',
            },
        )
    return jsonify(result)


@bp.get("/api/frida/scripts")
@auth.login_required
def list_scripts():
    return jsonify({"ok": True, "scripts": frida_manager.list_scripts()})


@bp.post("/api/frida/scripts")
@auth.login_required
@auth.csrf_protect
def save_script():
    d = request.get_json(silent=True) or {}
    result, err = _wrap(frida_manager.save_script, d.get("name", ""), d.get("source", ""))
    if err:
        return err
    auth.audit_log("frida_script_save", {
        "name": result["name"],
        "script_sha256": frida_manager.script_hash(d.get("source", "")),
    })
    return jsonify(result)


@bp.delete("/api/frida/scripts/<name>")
@auth.login_required
@auth.csrf_protect
def delete_script(name):
    result, err = _wrap(frida_manager.delete_script, name)
    if err:
        return err
    auth.audit_log("frida_script_delete", {"name": name})
    return jsonify(result)
