from flask import Blueprint, jsonify, request

import auth
from adb import battery as adb_battery
from adb import clipboard as adb_clipboard
from adb import manager as adb_manager
from adb import permissions as adb_permissions

bp = Blueprint("battery", __name__)


def _wrap(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except adb_manager.AdbNotInstalledError:
        return None, (jsonify({"ok": False, "error": "adb_not_installed"}), 503)
    except adb_manager.AdbError as exc:
        return None, (jsonify({"ok": False, "error": str(exc)}), 400)


@bp.get("/api/devices/<serial>/hardware")
@auth.login_required
def hardware(serial):
    result, err = _wrap(adb_battery.get_hardware_detail, serial)
    return err or jsonify({"ok": True, "hardware": result})


@bp.get("/api/devices/<serial>/packages/<package>/permissions")
@auth.login_required
def permissions_detail(serial, package):
    result, err = _wrap(adb_permissions.get_permission_detail, serial, package)
    return err or jsonify({"ok": True, "permissions": result})


@bp.post("/api/devices/<serial>/packages/<package>/permissions/grant")
@auth.login_required
@auth.csrf_protect
def permissions_grant(serial, package):
    permission = (request.get_json(silent=True) or {}).get("permission", "")
    result, err = _wrap(adb_permissions.grant_permission, serial, package, permission)
    if err:
        return err
    auth.audit_log("permission_grant", {"serial": serial, "package": package, "permission": permission})
    return jsonify(result)


@bp.post("/api/devices/<serial>/packages/<package>/permissions/revoke")
@auth.login_required
@auth.csrf_protect
def permissions_revoke(serial, package):
    permission = (request.get_json(silent=True) or {}).get("permission", "")
    result, err = _wrap(adb_permissions.revoke_permission, serial, package, permission)
    if err:
        return err
    auth.audit_log("permission_revoke", {"serial": serial, "package": package, "permission": permission})
    return jsonify(result)


@bp.get("/api/devices/<serial>/clipboard")
@auth.login_required
def clipboard_get(serial):
    result, err = _wrap(adb_clipboard.get_clipboard, serial)
    return err or jsonify(result)


@bp.post("/api/devices/<serial>/clipboard")
@auth.login_required
@auth.csrf_protect
def clipboard_set(serial):
    text = (request.get_json(silent=True) or {}).get("text", "")
    result, err = _wrap(adb_clipboard.set_clipboard, serial, text)
    if err:
        return err
    auth.audit_log("clipboard_write", {"serial": serial, "length": len(text)})
    return jsonify(result)


@bp.get("/api/devices/<serial>/clipboard/history")
@auth.login_required
def clipboard_history(serial):
    return jsonify({"ok": True, "history": adb_clipboard.get_clipboard_history(serial)})
