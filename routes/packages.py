import shutil
import tempfile
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file
from werkzeug.utils import secure_filename

import auth
import config
from adb import manager as adb_manager
from adb import packages as adb_packages

bp = Blueprint("packages", __name__)


def _wrap(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except adb_manager.AdbNotInstalledError:
        return None, (jsonify({"ok": False, "error": "adb_not_installed"}), 503)
    except adb_manager.AdbError as exc:
        return None, (jsonify({"ok": False, "error": str(exc)}), 400)


@bp.get("/api/devices/<serial>/packages")
@auth.login_required
def list_packages(serial):
    result, err = _wrap(adb_packages.list_packages, serial)
    if err:
        return err
    return jsonify({"ok": True, "packages": result})


@bp.get("/api/devices/<serial>/packages/<package>/size")
@auth.login_required
def package_size(serial, package):
    path = adb_packages.get_apk_path(serial, package)
    if not path:
        return jsonify({"ok": False, "error": "not_found"}), 404
    size = adb_packages.get_apk_size(serial, path)
    return jsonify({"ok": True, "size": size, "path": path})


@bp.post("/api/devices/<serial>/packages/install")
@auth.login_required
@auth.csrf_protect
def install(serial):
    files = request.files.getlist("apk")
    if not files:
        return jsonify({"ok": False, "error": "missing_apk"}), 400
    with tempfile.TemporaryDirectory(dir=config.TEMP_DIR) as tmp:
        local_paths = []
        for f in files:
            name = secure_filename(f.filename or "app.apk")
            local_path = Path(tmp) / name
            f.save(local_path)
            local_paths.append(local_path)
        if len(local_paths) > 1:
            result, err = _wrap(adb_packages.install_multiple_apks, serial, local_paths)
        else:
            result, err = _wrap(adb_packages.install_apk, serial, local_paths[0])
    if err:
        return err
    auth.audit_log("package_install", {"serial": serial, "files": [f.filename for f in files]})
    status = 200 if result["ok"] else 500
    return jsonify(result), status


@bp.post("/api/devices/<serial>/packages/<package>/uninstall")
@auth.login_required
@auth.csrf_protect
def uninstall(serial, package):
    keep_data = bool((request.get_json(silent=True) or {}).get("keep_data", False))
    result, err = _wrap(adb_packages.uninstall_apk, serial, package, keep_data)
    if err:
        return err
    auth.audit_log("package_uninstall", {"serial": serial, "package": package, "keep_data": keep_data})
    return jsonify(result)


def _make_action_route(name, fn):
    @auth.login_required
    @auth.csrf_protect
    def handler(serial, package):
        result, err = _wrap(fn, serial, package)
        if err:
            return err
        auth.audit_log(f"package_{name}", {"serial": serial, "package": package})
        return jsonify(result)
    handler.__name__ = f"package_{name}"
    return handler


bp.add_url_rule("/api/devices/<serial>/packages/<package>/disable", view_func=_make_action_route("disable", adb_packages.disable_package), methods=["POST"])
bp.add_url_rule("/api/devices/<serial>/packages/<package>/enable", view_func=_make_action_route("enable", adb_packages.enable_package), methods=["POST"])
bp.add_url_rule("/api/devices/<serial>/packages/<package>/clear-data", view_func=_make_action_route("clear_data", adb_packages.clear_data), methods=["POST"])
bp.add_url_rule("/api/devices/<serial>/packages/<package>/force-stop", view_func=_make_action_route("force_stop", adb_packages.force_stop), methods=["POST"])
bp.add_url_rule("/api/devices/<serial>/packages/<package>/launch", view_func=_make_action_route("launch", adb_packages.launch_app), methods=["POST"])


@bp.get("/api/devices/<serial>/packages/<package>/pull")
@auth.login_required
def pull_apk(serial, package):
    tmp_dir = tempfile.mkdtemp(dir=config.TEMP_DIR)
    local_path, err = _wrap(adb_packages.pull_apk, serial, package, Path(tmp_dir))
    if err:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return err
    auth.audit_log("package_pull_apk", {"serial": serial, "package": package})
    response = send_file(local_path, as_attachment=True, download_name=local_path.name)

    @response.call_on_close
    def _cleanup():
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return response
