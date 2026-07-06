from flask import Blueprint, jsonify, request

import auth
from adb import manager as adb_manager
from adb import process_manager as adb_process_manager

bp = Blueprint("process_manager", __name__)


def _wrap(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except adb_manager.AdbNotInstalledError:
        return None, (jsonify({"ok": False, "error": "adb_not_installed"}), 503)
    except adb_manager.AdbError as exc:
        return None, (jsonify({"ok": False, "error": str(exc)}), 400)


@bp.get("/api/devices/<serial>/processes")
@auth.login_required
def list_processes(serial):
    result, err = _wrap(adb_process_manager.list_processes, serial)
    return err or jsonify({"ok": True, **result})


@bp.get("/api/devices/<serial>/foreground-app")
@auth.login_required
def foreground_app(serial):
    result, err = _wrap(adb_process_manager.get_foreground_app, serial)
    return err or jsonify({"ok": True, **result})


@bp.post("/api/devices/<serial>/processes/<int:pid>/kill")
@auth.login_required
@auth.csrf_protect
def kill_process(serial, pid):
    sig = (request.get_json(silent=True) or {}).get("signal", "TERM")
    result, err = _wrap(adb_process_manager.kill_process, serial, pid, sig)
    if err:
        return err
    auth.audit_log("process_kill", {"serial": serial, "pid": pid, "signal": sig})
    return jsonify(result)
