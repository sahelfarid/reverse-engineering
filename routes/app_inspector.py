from flask import Blueprint, jsonify

import auth
from adb import app_inspector as adb_inspector
from adb import manager as adb_manager
from adb import packages as adb_packages

bp = Blueprint("app_inspector", __name__)


@bp.get("/api/devices/<serial>/packages/<package>/inspect")
@auth.login_required
def inspect(serial, package):
    try:
        detail = adb_inspector.get_app_detail(serial, package)
    except adb_manager.AdbNotInstalledError:
        return jsonify({"ok": False, "error": "adb_not_installed"}), 503
    except adb_manager.AdbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "detail": detail})


@bp.post("/api/devices/<serial>/packages/<package>/restart")
@auth.login_required
@auth.csrf_protect
def restart(serial, package):
    try:
        result = adb_packages.restart_app(serial, package)
    except adb_manager.AdbNotInstalledError:
        return jsonify({"ok": False, "error": "adb_not_installed"}), 503
    except adb_manager.AdbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    auth.audit_log("package_restart", {"serial": serial, "package": package})
    return jsonify(result)
