import shutil
import tempfile
from pathlib import Path

from flask import Blueprint, Response, jsonify, request, send_file

import auth
import config
from adb import files as adb_files
from adb import manager as adb_manager
from adb import screen as adb_screen

bp = Blueprint("screen", __name__)


def _wrap(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except adb_manager.AdbNotInstalledError:
        return None, (jsonify({"ok": False, "error": "adb_not_installed"}), 503)
    except adb_manager.AdbError as exc:
        return None, (jsonify({"ok": False, "error": str(exc)}), 400)


@bp.get("/api/devices/<serial>/screen/screenshot")
@auth.login_required
def screenshot(serial):
    png_bytes, err = _wrap(adb_screen.take_screenshot, serial)
    if err:
        return err
    return Response(png_bytes, mimetype="image/png")


@bp.post("/api/devices/<serial>/screen/record/start")
@auth.login_required
@auth.csrf_protect
def record_start(serial):
    data = request.get_json(silent=True) or {}
    time_limit = int(data.get("time_limit_sec", 180))
    result, err = _wrap(adb_screen.start_recording, serial, time_limit_sec=time_limit)
    if err:
        return err
    auth.audit_log("screen_record_start", {"serial": serial, "time_limit_sec": time_limit})
    return jsonify(result)


@bp.post("/api/devices/<serial>/screen/record/stop")
@auth.login_required
@auth.csrf_protect
def record_stop(serial):
    result, err = _wrap(adb_screen.stop_recording, serial)
    if err:
        return err
    auth.audit_log("screen_record_stop", {"serial": serial})
    return jsonify(result)


@bp.get("/api/devices/<serial>/screen/record/status")
@auth.login_required
def record_status(serial):
    return jsonify(adb_screen.recording_status(serial))


@bp.get("/api/devices/<serial>/screen/record/pull")
@auth.login_required
def record_pull(serial):
    remote_path = request.args.get("path", "/sdcard/adbpanel_record.mp4")
    tmp_dir = tempfile.mkdtemp(dir=config.TEMP_DIR)
    local_path, err = _wrap(adb_files.pull_file, serial, remote_path, Path(tmp_dir))
    if err:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return err
    response = send_file(local_path, as_attachment=True, download_name=local_path.name)

    @response.call_on_close
    def _cleanup():
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return response


def _simple_action_route(name, fn, parse_args=None):
    @auth.login_required
    @auth.csrf_protect
    def handler(serial):
        data = request.get_json(silent=True) or {}
        args = parse_args(data) if parse_args else ()
        result, err = _wrap(fn, serial, *args)
        if err:
            return err
        auth.audit_log(f"screen_{name}", {"serial": serial, "args": args})
        return jsonify(result)
    handler.__name__ = f"screen_{name}"
    return handler


bp.add_url_rule("/api/devices/<serial>/screen/rotate", view_func=_simple_action_route(
    "rotate", adb_screen.set_rotation, lambda d: (int(d.get("degrees", 0)),)), methods=["POST"])
bp.add_url_rule("/api/devices/<serial>/screen/auto-rotate", view_func=_simple_action_route(
    "auto_rotate", adb_screen.unlock_auto_rotation), methods=["POST"])
bp.add_url_rule("/api/devices/<serial>/screen/wake", view_func=_simple_action_route(
    "wake", adb_screen.wake_device), methods=["POST"])
bp.add_url_rule("/api/devices/<serial>/screen/sleep", view_func=_simple_action_route(
    "sleep", adb_screen.sleep_device), methods=["POST"])
bp.add_url_rule("/api/devices/<serial>/screen/brightness", view_func=_simple_action_route(
    "brightness", adb_screen.set_brightness, lambda d: (int(d.get("level", 128)),)), methods=["POST"])
