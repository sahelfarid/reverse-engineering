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
    session_id, err = _wrap(frida_manager.attach, serial, target, source)
    if err:
        return err
    auth.audit_log("frida_attach", {
        "serial": serial,
        "target": target,
        "script_name": script_name,
        "script_sha256": frida_manager.script_hash(source),
    })
    return jsonify({"ok": True, "session_id": session_id})


@bp.get("/api/frida/sessions")
@auth.login_required
def sessions():
    return jsonify({"ok": True, "sessions": frida_manager.list_sessions()})


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


@bp.post("/api/frida/sessions/<session_id>/detach")
@auth.login_required
@auth.csrf_protect
def detach(session_id):
    result, err = _wrap(frida_manager.detach, session_id)
    if err:
        return err
    auth.audit_log("frida_detach", {"session_id": session_id})
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
