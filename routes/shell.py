from flask import Blueprint, jsonify, request

import auth
from adb import manager as adb_manager
from adb import shell as adb_shell

bp = Blueprint("shell", __name__)


@bp.get("/api/devices/<serial>/shell/su-available")
@auth.login_required
def su_available(serial):
    try:
        available = adb_shell.su_available(serial)
    except adb_manager.AdbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "available": available})


@bp.post("/api/devices/<serial>/shell/exec")
@auth.login_required
@auth.csrf_protect
def shell_exec(serial):
    data = request.get_json(silent=True) or {}
    command = data.get("command", "")
    use_su = bool(data.get("use_su", False))
    try:
        result = adb_shell.run_command(serial, command, use_su=use_su)
    except adb_manager.AdbNotInstalledError:
        return jsonify({"ok": False, "error": "adb_not_installed"}), 503
    except adb_manager.AdbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    auth.audit_log("shell_exec", {
        "serial": serial,
        "use_su": use_su,
        "command": command[:500],
        "returncode": result["returncode"],
    })
    return jsonify({"ok": True, "result": result})
