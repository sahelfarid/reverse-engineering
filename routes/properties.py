from flask import Blueprint, jsonify

import auth
from adb import manager as adb_manager
from adb import properties as adb_properties

bp = Blueprint("properties", __name__)


@bp.get("/api/devices/<serial>/properties")
@auth.login_required
def get_properties(serial):
    try:
        result = adb_properties.get_properties(serial)
    except adb_manager.AdbNotInstalledError:
        return jsonify({"ok": False, "error": "adb_not_installed"}), 503
    except adb_manager.AdbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})
