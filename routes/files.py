import shutil
import tempfile
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file
from werkzeug.utils import secure_filename

import auth
import config
from adb import files as adb_files
from adb import manager as adb_manager

bp = Blueprint("files", __name__)


def _handle_adb_errors(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except adb_manager.AdbNotInstalledError:
        return None, (jsonify({"ok": False, "error": "adb_not_installed"}), 503)
    except adb_manager.AdbError as exc:
        return None, (jsonify({"ok": False, "error": str(exc)}), 400)


@bp.get("/api/devices/<serial>/files/browse")
@auth.login_required
def browse(serial):
    path = request.args.get("path", "/sdcard")
    result, err = _handle_adb_errors(adb_files.list_directory, serial, path)
    if err:
        return err
    status = 200 if result["ok"] else 404
    return jsonify(result), status


@bp.get("/api/devices/<serial>/files/search")
@auth.login_required
def search(serial):
    root = request.args.get("path", "/sdcard")
    query = request.args.get("query", "")
    if not query:
        return jsonify({"ok": False, "error": "missing_query"}), 400
    result, err = _handle_adb_errors(adb_files.search_path, serial, root, query)
    if err:
        return err
    return jsonify(result)


@bp.post("/api/devices/<serial>/files/mkdir")
@auth.login_required
@auth.csrf_protect
def mkdir(serial):
    data = request.get_json(silent=True) or {}
    path = data.get("path", "")
    if not path:
        return jsonify({"ok": False, "error": "missing_path"}), 400
    result, err = _handle_adb_errors(adb_files.mkdir_path, serial, path)
    if err:
        return err
    auth.audit_log("file_mkdir", {"serial": serial, "path": path})
    return jsonify(result)


@bp.post("/api/devices/<serial>/files/delete")
@auth.login_required
@auth.csrf_protect
def delete(serial):
    data = request.get_json(silent=True) or {}
    path = data.get("path", "")
    recursive = bool(data.get("recursive", False))
    if not path:
        return jsonify({"ok": False, "error": "missing_path"}), 400
    result, err = _handle_adb_errors(adb_files.delete_path, serial, path, recursive)
    if err:
        return err
    auth.audit_log("file_delete", {"serial": serial, "path": path, "recursive": recursive})
    return jsonify(result)


@bp.post("/api/devices/<serial>/files/rename")
@auth.login_required
@auth.csrf_protect
def rename(serial):
    data = request.get_json(silent=True) or {}
    path, new_name = data.get("path", ""), data.get("new_name", "")
    if not path or not new_name:
        return jsonify({"ok": False, "error": "missing_fields"}), 400
    result, err = _handle_adb_errors(adb_files.rename_path, serial, path, new_name)
    if err:
        return err
    auth.audit_log("file_rename", {"serial": serial, "path": path, "new_name": new_name})
    return jsonify(result)


@bp.post("/api/devices/<serial>/files/move")
@auth.login_required
@auth.csrf_protect
def move(serial):
    data = request.get_json(silent=True) or {}
    src, dest = data.get("src", ""), data.get("dest", "")
    if not src or not dest:
        return jsonify({"ok": False, "error": "missing_fields"}), 400
    result, err = _handle_adb_errors(adb_files.move_path, serial, src, dest)
    if err:
        return err
    auth.audit_log("file_move", {"serial": serial, "src": src, "dest": dest})
    return jsonify(result)


@bp.post("/api/devices/<serial>/files/copy")
@auth.login_required
@auth.csrf_protect
def copy(serial):
    data = request.get_json(silent=True) or {}
    src, dest = data.get("src", ""), data.get("dest", "")
    if not src or not dest:
        return jsonify({"ok": False, "error": "missing_fields"}), 400
    result, err = _handle_adb_errors(adb_files.copy_path, serial, src, dest)
    if err:
        return err
    auth.audit_log("file_copy", {"serial": serial, "src": src, "dest": dest})
    return jsonify(result)


@bp.post("/api/devices/<serial>/files/upload")
@auth.login_required
@auth.csrf_protect
def upload(serial):
    settings = config.load_settings()
    max_bytes = int(settings.get("max_upload_mb", 200)) * 1024 * 1024
    if request.content_length and request.content_length > max_bytes:
        return jsonify({"ok": False, "error": "file_too_large"}), 413

    remote_dir = request.form.get("remote_dir", "/sdcard")
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"ok": False, "error": "missing_file"}), 400

    filename = secure_filename(uploaded.filename)
    if not filename:
        return jsonify({"ok": False, "error": "invalid_filename"}), 400

    with tempfile.TemporaryDirectory(dir=config.TEMP_DIR) as tmp:
        local_path = Path(tmp) / filename
        uploaded.save(local_path)
        result, err = _handle_adb_errors(adb_files.push_file, serial, local_path, remote_dir)
        if err:
            return err
    auth.audit_log("file_upload", {"serial": serial, "remote_dir": remote_dir, "filename": filename})
    return jsonify(result)


@bp.get("/api/devices/<serial>/files/preview")
@auth.login_required
def preview(serial):
    path = request.args.get("path", "")
    if not path:
        return jsonify({"ok": False, "error": "missing_path"}), 400
    kind = adb_files.preview_kind(path)
    if kind == "text":
        result, err = _handle_adb_errors(adb_files.read_text_preview, serial, path)
        if err:
            return err
        return jsonify({**result, "kind": "text"})
    if kind == "image":
        tmp_dir = tempfile.mkdtemp(dir=config.TEMP_DIR)
        local_path, err = _handle_adb_errors(adb_files.pull_file, serial, path, Path(tmp_dir))
        if err:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return err

        response = send_file(local_path, as_attachment=False)

        @response.call_on_close
        def _remove_tmp():
            shutil.rmtree(tmp_dir, ignore_errors=True)

        return response
    return jsonify({"ok": False, "error": "preview_not_supported", "kind": kind})


@bp.get("/api/devices/<serial>/files/download")
@auth.login_required
def download(serial):
    path = request.args.get("path", "")
    if not path:
        return jsonify({"ok": False, "error": "missing_path"}), 400
    tmp_dir = tempfile.mkdtemp(dir=config.TEMP_DIR)
    local_path, err = _handle_adb_errors(adb_files.pull_file, serial, path, Path(tmp_dir))
    if err:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return err
    auth.audit_log("file_download", {"serial": serial, "path": path})
    response = send_file(local_path, as_attachment=True, download_name=local_path.name)

    @response.call_on_close
    def _remove_tmp():
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return response


@bp.get("/api/devices/<serial>/files/download-folder")
@auth.login_required
def download_folder(serial):
    path = request.args.get("path", "")
    if not path:
        return jsonify({"ok": False, "error": "missing_path"}), 400
    folder_name = path.rstrip("/").rsplit("/", 1)[-1] or "root"
    tmp_dir = tempfile.mkdtemp(dir=config.TEMP_DIR)
    pulled_dir = Path(tmp_dir) / "pulled"
    pulled_dir.mkdir()

    def _pull():
        proc = adb_manager.run(["-s", serial, "pull", path, str(pulled_dir)], timeout=600)
        if proc.returncode != 0:
            raise adb_manager.AdbError(f"pull failed: {proc.stderr.strip()[:300]}")

    _, err = _handle_adb_errors(_pull)
    if err:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return err

    pulled_root = pulled_dir / folder_name
    zip_source = pulled_root if pulled_root.is_dir() else pulled_dir
    zip_base = Path(tmp_dir) / "bundle"
    zip_path = adb_files.zip_folder(zip_source, zip_base)

    auth.audit_log("file_download_folder", {"serial": serial, "path": path})
    response = send_file(zip_path, as_attachment=True, download_name=f"{folder_name}.zip")

    @response.call_on_close
    def _remove_tmp():
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return response
