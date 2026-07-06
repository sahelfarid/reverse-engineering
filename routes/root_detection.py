from flask import Blueprint, jsonify

import auth
from adb import manager as adb_manager
from adb import root_detection

bp = Blueprint("root_detection", __name__)


@bp.get("/api/devices/<serial>/integrity")
@auth.login_required
def integrity(serial):
    # Read-only (no device state changes), so no CSRF -- same as properties.
    try:
        report = root_detection.get_integrity_report(serial)
    except adb_manager.AdbNotInstalledError:
        return jsonify({"ok": False, "error": "adb_not_installed"}), 503
    except adb_manager.AdbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "report": report})
