from flask import Blueprint, jsonify, request

import auth
from adb import manager as adb_manager
from adb import root_checker

bp = Blueprint("root_checker", __name__)


def _clamp_duration(value, default=4.0, low=1.0, high=15.0) -> float:
    try:
        return max(low, min(float(value), high))
    except (TypeError, ValueError):
        return default


@bp.get("/api/devices/<serial>/packages/<package>/rootcheck")
@auth.login_required
def rootcheck_static(serial, package):
    # GET is static-only: no spawn/attach side effects, so it stays
    # read-only/idempotent and needs no CSRF (same reasoning as properties
    # and root_detection's GET routes).
    try:
        report = root_checker.get_report(serial, package, run_dynamic=False)
    except adb_manager.AdbNotInstalledError:
        return jsonify({"ok": False, "error": "adb_not_installed"}), 503
    except adb_manager.AdbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "report": report})


@bp.post("/api/devices/<serial>/packages/<package>/rootcheck")
@auth.login_required
@auth.csrf_protect
def rootcheck_full(serial, package):
    # POST additionally spawns the app under Frida to observe root checks at
    # runtime -- a real side effect (kills/restarts the app), so it's gated
    # behind CSRF like other mutating routes.
    d = request.get_json(silent=True) or {}
    duration = _clamp_duration(d.get("duration_sec", 4.0))
    try:
        report = root_checker.get_report(serial, package, run_dynamic=True, dynamic_duration_sec=duration)
    except adb_manager.AdbNotInstalledError:
        return jsonify({"ok": False, "error": "adb_not_installed"}), 503
    except adb_manager.AdbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    auth.audit_log("root_check", {"serial": serial, "package": package, "verdict": report["verdict"]})
    return jsonify({"ok": True, "report": report})
