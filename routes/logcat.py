import json

from flask import Blueprint, Response, jsonify, request, stream_with_context

import auth
from adb import logcat as adb_logcat
from adb import manager as adb_manager

bp = Blueprint("logcat", __name__)


@bp.get("/api/devices/<serial>/logcat/stream")
@auth.login_required
def stream(serial):
    tag = request.args.get("tag") or None
    pid = request.args.get("pid") or None
    package = request.args.get("package") or None
    min_level = request.args.get("min_level") or None
    query = request.args.get("query") or None

    if package and not pid:
        pid = adb_logcat.resolve_pid(serial, package)

    def generate():
        try:
            for entry in adb_logcat.stream_logcat(serial, tag, pid, min_level, query):
                yield f"data: {json.dumps(entry)}\n\n"
        except adb_manager.AdbError as exc:
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                     headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@bp.post("/api/devices/<serial>/logcat/clear")
@auth.login_required
@auth.csrf_protect
def clear(serial):
    try:
        result = adb_logcat.clear_logcat(serial)
    except adb_manager.AdbNotInstalledError:
        return jsonify({"ok": False, "error": "adb_not_installed"}), 503
    auth.audit_log("logcat_clear", {"serial": serial})
    return jsonify(result)
