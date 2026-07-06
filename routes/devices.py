from flask import Blueprint, jsonify

import auth
from adb import devices as adb_devices
from adb import manager as adb_manager

bp = Blueprint("devices", __name__)


@bp.get("/api/devices")
@auth.login_required
def get_devices():
    try:
        entries = adb_devices.list_devices()
        entries += adb_devices.list_fastboot_devices()
    except adb_manager.AdbNotInstalledError:
        return jsonify({"ok": False, "error": "adb_not_installed"}), 503
    return jsonify({"ok": True, "devices": entries})


@bp.get("/api/devices/<serial>")
@auth.login_required
def get_device_detail(serial):
    try:
        detail = adb_devices.get_device_detail(serial)
    except adb_manager.AdbNotInstalledError:
        return jsonify({"ok": False, "error": "adb_not_installed"}), 503
    except adb_manager.AdbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "device": detail})
