from flask import Blueprint, jsonify, request

import auth
from adb import frida_manager as adb_frida
from adb import manager as adb_manager
from adb import ssl_pinning

bp = Blueprint("ssl_pinning", __name__)


def _clamp_duration(value, default=4.0, low=1.0, high=15.0) -> float:
    try:
        return max(low, min(float(value), high))
    except (TypeError, ValueError):
        return default


@bp.post("/api/devices/<serial>/packages/<package>/sslpinning/detect")
@auth.login_required
@auth.csrf_protect
def detect(serial, package):
    d = request.get_json(silent=True) or {}
    run_dynamic = bool(d.get("dynamic", True))
    duration = _clamp_duration(d.get("duration_sec", 4.0))
    try:
        report = ssl_pinning.get_detection_report(serial, package, run_dynamic=run_dynamic, dynamic_duration_sec=duration)
    except adb_manager.AdbNotInstalledError:
        return jsonify({"ok": False, "error": "adb_not_installed"}), 503
    except adb_manager.AdbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    auth.audit_log("ssl_pinning_detect", {
        "serial": serial, "package": package, "verdict": report["verdict"], "dynamic": run_dynamic,
    })
    return jsonify({"ok": True, "report": report})


@bp.post("/api/devices/<serial>/frida/sslpinning/bypass")
@auth.login_required
@auth.csrf_protect
def bypass(serial):
    d = request.get_json(silent=True) or {}
    # Bypass genuinely changes app behavior (accept-all TLS trust), so it
    # requires an explicit, separate acknowledgment beyond just being logged
    # in -- not just heavily audited after the fact.
    if d.get("confirm") is not True:
        return jsonify({
            "ok": False, "error": "confirmation_required",
            "message": "Set confirm: true to acknowledge you are authorized to test this app's traffic.",
        }), 400

    target = d.get("target")
    if d.get("spawn"):
        target = {"spawn": d.get("spawn")}
    if not target:
        return jsonify({"ok": False, "error": "missing_target"}), 400

    try:
        result = ssl_pinning.attach_bypass(serial, target, d.get("script_name"), d.get("script_source"))
    except adb_manager.AdbNotInstalledError:
        return jsonify({"ok": False, "error": "adb_not_installed"}), 503
    except adb_manager.AdbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    auth.audit_log("ssl_pinning_bypass", {
        "serial": serial, "target": target, "script_name": d.get("script_name"),
        "script_sha256": result["script_sha256"], "authorized": True,
    })
    return jsonify(result)


@bp.get("/api/frida/sslpinning/scripts")
@auth.login_required
def list_scripts():
    return jsonify({"ok": True, "scripts": ssl_pinning.list_scripts()})


@bp.post("/api/frida/sslpinning/scripts")
@auth.login_required
@auth.csrf_protect
def save_script():
    d = request.get_json(silent=True) or {}
    try:
        result = ssl_pinning.save_script(d.get("name", ""), d.get("source", ""))
    except adb_manager.AdbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    auth.audit_log("ssl_pinning_script_save", {
        "name": result["name"], "script_sha256": adb_frida.script_hash(d.get("source", "")),
    })
    return jsonify(result)


@bp.delete("/api/frida/sslpinning/scripts/<name>")
@auth.login_required
@auth.csrf_protect
def delete_script(name):
    try:
        result = ssl_pinning.delete_script(name)
    except adb_manager.AdbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    auth.audit_log("ssl_pinning_script_delete", {"name": name})
    return jsonify(result)
