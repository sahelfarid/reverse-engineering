from flask import Blueprint, jsonify, request

import auth
from adb import manager as adb_manager
from adb import network as adb_network
from adb import wireless as adb_wireless

bp = Blueprint("network", __name__)


def _wrap(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except adb_manager.AdbNotInstalledError:
        return None, (jsonify({"ok": False, "error": "adb_not_installed"}), 503)
    except adb_manager.AdbError as exc:
        return None, (jsonify({"ok": False, "error": str(exc)}), 400)


@bp.get("/api/devices/<serial>/network")
@auth.login_required
def network_info(serial):
    result, err = _wrap(adb_network.get_network_info, serial)
    return err or jsonify({"ok": True, "network": result})


@bp.post("/api/devices/<serial>/network/ping")
@auth.login_required
@auth.csrf_protect
def ping(serial):
    d = request.get_json(silent=True) or {}
    result, err = _wrap(adb_network.ping_from_device, serial, d.get("host", ""), d.get("count", 4))
    return err or jsonify(result)


@bp.get("/api/forwards")
@auth.login_required
def forwards_list():
    result, err = _wrap(adb_network.list_forwards)
    return err or jsonify({"ok": True, "forwards": result})


@bp.post("/api/devices/<serial>/forward")
@auth.login_required
@auth.csrf_protect
def forward_add(serial):
    d = request.get_json(silent=True) or {}
    result, err = _wrap(adb_network.add_forward, serial, d.get("local", ""), d.get("remote", ""))
    if err:
        return err
    auth.audit_log("forward_add", {"serial": serial, "local": d.get("local"), "remote": d.get("remote")})
    return jsonify(result)


@bp.post("/api/forward/remove")
@auth.login_required
@auth.csrf_protect
def forward_remove():
    d = request.get_json(silent=True) or {}
    result, err = _wrap(adb_network.remove_forward, d.get("local", ""))
    if err:
        return err
    auth.audit_log("forward_remove", {"local": d.get("local")})
    return jsonify(result)


@bp.get("/api/devices/<serial>/reverse")
@auth.login_required
def reverse_list(serial):
    result, err = _wrap(adb_network.list_reverses, serial)
    return err or jsonify({"ok": True, "reverses": result})


@bp.post("/api/devices/<serial>/reverse")
@auth.login_required
@auth.csrf_protect
def reverse_add(serial):
    d = request.get_json(silent=True) or {}
    result, err = _wrap(adb_network.add_reverse, serial, d.get("remote", ""), d.get("local", ""))
    if err:
        return err
    auth.audit_log("reverse_add", {"serial": serial, "remote": d.get("remote"), "local": d.get("local")})
    return jsonify(result)


@bp.post("/api/devices/<serial>/reverse/remove")
@auth.login_required
@auth.csrf_protect
def reverse_remove(serial):
    d = request.get_json(silent=True) or {}
    result, err = _wrap(adb_network.remove_reverse, serial, d.get("remote", ""))
    if err:
        return err
    auth.audit_log("reverse_remove", {"serial": serial, "remote": d.get("remote")})
    return jsonify(result)


@bp.post("/api/devices/<serial>/wireless/enable-tcpip")
@auth.login_required
@auth.csrf_protect
def enable_tcpip(serial):
    d = request.get_json(silent=True) or {}
    result, err = _wrap(adb_wireless.enable_tcpip, serial, d.get("port", 5555))
    if err:
        return err
    auth.audit_log("wireless_enable_tcpip", {"serial": serial, "port": d.get("port", 5555)})
    return jsonify(result)


@bp.get("/api/devices/<serial>/wireless/address")
@auth.login_required
def wireless_address(serial):
    try:
        port = int(request.args.get("port", 5555))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid_port"}), 400
    result, err = _wrap(adb_wireless.get_device_wifi_address, serial, port)
    return err or jsonify({"ok": True, "address": result})


@bp.post("/api/wireless/connect")
@auth.login_required
@auth.csrf_protect
def wireless_connect():
    d = request.get_json(silent=True) or {}
    result, err = _wrap(adb_wireless.connect, d.get("address", ""))
    if err:
        return err
    auth.audit_log("wireless_connect", {"address": d.get("address")})
    return jsonify(result)


@bp.post("/api/wireless/disconnect")
@auth.login_required
@auth.csrf_protect
def wireless_disconnect():
    d = request.get_json(silent=True) or {}
    result, err = _wrap(adb_wireless.disconnect, d.get("address", ""))
    if err:
        return err
    auth.audit_log("wireless_disconnect", {"address": d.get("address")})
    return jsonify(result)


@bp.get("/api/wireless/known")
@auth.login_required
def known_devices():
    return jsonify({"ok": True, "devices": adb_wireless.list_known_devices()})


@bp.post("/api/wireless/known")
@auth.login_required
@auth.csrf_protect
def known_device_save():
    d = request.get_json(silent=True) or {}
    result = adb_wireless.save_known_device(d.get("name", ""), d.get("address", ""))
    if result.get("ok"):
        auth.audit_log("wireless_known_save", {"name": d.get("name"), "address": d.get("address")})
    return jsonify(result)


@bp.delete("/api/wireless/known/<name>")
@auth.login_required
@auth.csrf_protect
def known_device_delete(name):
    result = adb_wireless.delete_known_device(name)
    auth.audit_log("wireless_known_delete", {"name": name})
    return jsonify(result)


@bp.post("/api/wireless/reconnect-all")
@auth.login_required
@auth.csrf_protect
def reconnect_all():
    results = adb_wireless.reconnect_known_devices()
    auth.audit_log("wireless_reconnect_all", {"count": len(results)})
    return jsonify({"ok": True, "results": results})
