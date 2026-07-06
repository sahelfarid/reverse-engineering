from flask import Blueprint, jsonify, request

import auth
from adb import automation as adb_automation
from adb import manager as adb_manager

bp = Blueprint("automation", __name__)


def _wrap(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except adb_manager.AdbNotInstalledError:
        return None, (jsonify({"ok": False, "error": "adb_not_installed"}), 503)
    except adb_manager.AdbError as exc:
        return None, (jsonify({"ok": False, "error": str(exc)}), 400)


@bp.post("/api/devices/<serial>/input/tap")
@auth.login_required
@auth.csrf_protect
def tap(serial):
    d = request.get_json(silent=True) or {}
    result, err = _wrap(adb_automation.tap, serial, d.get("x", 0), d.get("y", 0))
    return err or jsonify(result)


@bp.post("/api/devices/<serial>/input/swipe")
@auth.login_required
@auth.csrf_protect
def swipe(serial):
    d = request.get_json(silent=True) or {}
    result, err = _wrap(adb_automation.swipe, serial, d.get("x1", 0), d.get("y1", 0),
                         d.get("x2", 0), d.get("y2", 0), d.get("duration_ms", 300))
    return err or jsonify(result)


@bp.post("/api/devices/<serial>/input/long-press")
@auth.login_required
@auth.csrf_protect
def long_press(serial):
    d = request.get_json(silent=True) or {}
    result, err = _wrap(adb_automation.long_press, serial, d.get("x", 0), d.get("y", 0), d.get("duration_ms", 800))
    return err or jsonify(result)


@bp.post("/api/devices/<serial>/input/text")
@auth.login_required
@auth.csrf_protect
def text(serial):
    d = request.get_json(silent=True) or {}
    result, err = _wrap(adb_automation.type_text, serial, d.get("text", ""))
    if err:
        return err
    auth.audit_log("input_text", {"serial": serial, "length": len(d.get("text", ""))})
    return jsonify(result)


@bp.post("/api/devices/<serial>/input/keyevent")
@auth.login_required
@auth.csrf_protect
def keyevent(serial):
    d = request.get_json(silent=True) or {}
    result, err = _wrap(adb_automation.keyevent, serial, d.get("code", ""))
    return err or jsonify(result)


@bp.get("/api/devices/<serial>/screen-size")
@auth.login_required
def screen_size(serial):
    result, err = _wrap(adb_automation.get_screen_size, serial)
    return err or jsonify({"ok": True, **result})


@bp.get("/api/macros")
@auth.login_required
def list_macros():
    return jsonify({"ok": True, "macros": adb_automation.list_macros()})


@bp.post("/api/macros")
@auth.login_required
@auth.csrf_protect
def save_macro():
    d = request.get_json(silent=True) or {}
    name, steps = d.get("name", ""), d.get("steps", [])
    if not name or not isinstance(steps, list):
        return jsonify({"ok": False, "error": "missing_fields"}), 400
    result, err = _wrap(adb_automation.save_macro, name, steps)
    if err:
        return err
    auth.audit_log("macro_save", {"name": name, "steps": len(steps)})
    return jsonify(result)


@bp.delete("/api/macros/<name>")
@auth.login_required
@auth.csrf_protect
def delete_macro(name):
    result = adb_automation.delete_macro(name)
    auth.audit_log("macro_delete", {"name": name})
    return jsonify(result)


@bp.post("/api/devices/<serial>/macros/<name>/play")
@auth.login_required
@auth.csrf_protect
def play_macro(serial, name):
    macros = adb_automation.list_macros()
    if name not in macros:
        return jsonify({"ok": False, "error": "macro_not_found"}), 404
    result, err = _wrap(adb_automation.play_macro, serial, macros[name])
    if err:
        return err
    auth.audit_log("macro_play", {"serial": serial, "name": name})
    return jsonify(result)
