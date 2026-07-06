import shutil
import tempfile
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

import auth
import config
from adb import backup as adb_backup
from adb import files as adb_files
from adb import jobs as adb_jobs
from adb import manager as adb_manager
from adb import packages as adb_packages

bp = Blueprint("backup", __name__)


def _wrap(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except adb_manager.AdbNotInstalledError:
        return None, (jsonify({"ok": False, "error": "adb_not_installed"}), 503)
    except adb_manager.AdbError as exc:
        return None, (jsonify({"ok": False, "error": str(exc)}), 400)


def _send_and_cleanup(local_path: Path, tmp_dir: str, download_name: str | None = None):
    response = send_file(local_path, as_attachment=True, download_name=download_name or local_path.name)
    # send_file()'s direct_passthrough=True makes Werkzeug skip the
    # ClosingIterator that calls Response.close() -- without this,
    # call_on_close() below would never fire (see docs/module-audits/files.md).
    response.direct_passthrough = False

    @response.call_on_close
    def _cleanup():
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return response


@bp.get("/api/backup/targets")
@auth.login_required
def targets():
    return jsonify({"ok": True, "targets": adb_backup.COMMON_EXPORT_TARGETS})


@bp.get("/api/devices/<serial>/backup/export/<key>")
@auth.login_required
def export_folder(serial, key):
    remote_path = adb_backup.resolve_export_path(key)
    if not remote_path:
        return jsonify({"ok": False, "error": "unknown_target"}), 404
    tmp_dir = tempfile.mkdtemp(dir=config.TEMP_DIR)
    pulled_dir = Path(tmp_dir) / "pulled"
    pulled_dir.mkdir()

    def _pull():
        proc = adb_manager.run(["-s", serial, "pull", remote_path, str(pulled_dir)], timeout=600)
        if proc.returncode != 0:
            raise adb_manager.AdbError(f"pull failed: {proc.stderr.strip()[:300]}")

    _, err = _wrap(_pull)
    if err:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return err

    folder_name = remote_path.rstrip("/").rsplit("/", 1)[-1]
    pulled_root = pulled_dir / folder_name
    zip_source = pulled_root if pulled_root.is_dir() else pulled_dir
    zip_path = adb_files.zip_folder(zip_source, Path(tmp_dir) / "bundle")
    auth.audit_log("backup_export_folder", {"serial": serial, "target": key})
    return _send_and_cleanup(zip_path, tmp_dir, f"{key}.zip")


@bp.get("/api/devices/<serial>/backup/logcat")
@auth.login_required
def export_logcat(serial):
    tmp_dir = tempfile.mkdtemp(dir=config.TEMP_DIR)
    local_path, err = _wrap(adb_backup.dump_logcat_to_file, serial, Path(tmp_dir))
    if err:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return err
    auth.audit_log("backup_export_logcat", {"serial": serial})
    return _send_and_cleanup(local_path, tmp_dir)


@bp.get("/api/devices/<serial>/backup/apk/<package>")
@auth.login_required
def export_apk(serial, package):
    tmp_dir = tempfile.mkdtemp(dir=config.TEMP_DIR)
    local_path, err = _wrap(adb_packages.pull_apk, serial, package, Path(tmp_dir))
    if err:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return err
    auth.audit_log("backup_export_apk", {"serial": serial, "package": package})
    return _send_and_cleanup(local_path, tmp_dir)


@bp.get("/api/devices/<serial>/backup/database")
@auth.login_required
def export_database(serial):
    package = request.args.get("package", "")
    db = request.args.get("db", "")
    if not package or not db:
        return jsonify({"ok": False, "error": "missing_fields"}), 400
    tmp_dir = tempfile.mkdtemp(dir=config.TEMP_DIR)
    local_path, err = _wrap(adb_backup.export_database, serial, package, db, Path(tmp_dir))
    if err:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return err
    auth.audit_log("backup_export_database", {"serial": serial, "package": package, "db": db})
    return _send_and_cleanup(local_path, tmp_dir)


@bp.get("/api/devices/<serial>/backup/app-data")
@auth.login_required
def export_app_data(serial):
    package = request.args.get("package", "")
    if not package:
        return jsonify({"ok": False, "error": "missing_package"}), 400
    tmp_dir = tempfile.mkdtemp(dir=config.TEMP_DIR)
    local_path, err = _wrap(adb_backup.export_app_data, serial, package, Path(tmp_dir))
    if err:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return err
    auth.audit_log("backup_export_app_data", {"serial": serial, "package": package})
    return _send_and_cleanup(local_path, tmp_dir, f"{package}_data.tar.gz")


@bp.get("/api/devices/<serial>/backup/app-data/async")
@auth.login_required
def export_app_data_async(serial):
    package = request.args.get("package", "")
    if not package:
        return jsonify({"ok": False, "error": "missing_package"}), 400
    tmp_dir = tempfile.mkdtemp(dir=config.TEMP_DIR)
    job_id = adb_jobs.create_job("app_data_export", label=package)

    def _run(job_id):
        try:
            local_path = adb_backup.export_app_data(serial, package, Path(tmp_dir))
            return {"file_path": str(local_path), "download_name": f"{package}_data.tar.gz", "tmp_dir": tmp_dir}
        except Exception:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise

    adb_jobs.run_in_background(job_id, _run)
    auth.audit_log("backup_export_app_data_async", {"serial": serial, "package": package})
    return jsonify({"ok": True, "job_id": job_id})
