from flask import Blueprint, jsonify, request

import auth
from adb import apktool_manager
from adb import jobs as adb_jobs
from adb import manager as adb_manager

bp = Blueprint("apktool", __name__)


def _wrap(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except adb_manager.AdbNotInstalledError:
        return None, (jsonify({"ok": False, "error": "adb_not_installed"}), 503)
    except adb_manager.AdbError as exc:
        return None, (jsonify({"ok": False, "error": str(exc)}), 400)


@bp.get("/api/apktool/status")
@auth.login_required
def status():
    return jsonify(apktool_manager.get_status())


@bp.post("/api/apktool/install")
@auth.login_required
@auth.csrf_protect
def install_apktool():
    jar, err = _wrap(apktool_manager.ensure_apktool)
    if err:
        return err
    status_data = apktool_manager.get_status()
    auth.audit_log("apktool_install", {"path": str(jar), "version": status_data["apktool"].get("version")})
    return jsonify({"ok": True, "status": status_data})


@bp.post("/api/devices/<serial>/apktool/decompile/<package>")
@auth.login_required
@auth.csrf_protect
def decompile(serial, package):
    job_id = adb_jobs.create_job("apktool_decompile", label=package)

    def _run(job_id):
        path = apktool_manager.decompile(serial, package, job_id=job_id)
        return {"project": package, "path": str(path)}

    adb_jobs.run_in_background(job_id, _run)
    auth.audit_log("apktool_decompile", {"serial": serial, "package": package, "job_id": job_id})
    return jsonify({"ok": True, "job_id": job_id})


@bp.get("/api/apktool/projects")
@auth.login_required
def projects():
    result, err = _wrap(apktool_manager.list_projects)
    return err or jsonify({"ok": True, "projects": result})


@bp.get("/api/apktool/projects/<project>/browse")
@auth.login_required
def browse(project):
    path = request.args.get("path", "")
    result, err = _wrap(apktool_manager.browse_project, project, path)
    return err or jsonify(result)


@bp.get("/api/apktool/projects/<project>/file")
@auth.login_required
def read_file(project):
    path = request.args.get("path", "")
    if not path:
        return jsonify({"ok": False, "error": "missing_path"}), 400
    content, err = _wrap(apktool_manager.read_project_file, project, path)
    return err or jsonify({"ok": True, "path": path, "content": content})


@bp.post("/api/apktool/projects/<project>/file")
@auth.login_required
@auth.csrf_protect
def write_file(project):
    path = request.args.get("path", "")
    if not path:
        return jsonify({"ok": False, "error": "missing_path"}), 400
    data = request.get_json(silent=True) or {}
    result, err = _wrap(apktool_manager.write_project_file, project, path, data.get("content", ""))
    if err:
        return err
    auth.audit_log("apktool_file_save", {"project": project, "path": path})
    return jsonify(result)


@bp.post("/api/apktool/projects/<project>/rebuild")
@auth.login_required
@auth.csrf_protect
def rebuild(project):
    job_id = adb_jobs.create_job("apktool_rebuild", label=project)

    def _run(job_id):
        path = apktool_manager.rebuild(project, job_id=job_id)
        return {"project": project, "signed_apk": str(path), "file_path": str(path), "download_name": path.name}

    adb_jobs.run_in_background(job_id, _run)
    auth.audit_log("apktool_rebuild", {"project": project, "job_id": job_id})
    return jsonify({"ok": True, "job_id": job_id})


@bp.post("/api/devices/<serial>/apktool/projects/<project>/reinstall")
@auth.login_required
@auth.csrf_protect
def reinstall(serial, project):
    signed_apk = apktool_manager.BUILDS_DIR / apktool_manager.validate_project(project) / "rebuilt-signed.apk"
    result, err = _wrap(apktool_manager.reinstall, serial, signed_apk)
    if err:
        return err
    auth.audit_log("apktool_reinstall", {"serial": serial, "project": project})
    status_code = 200 if result.get("ok") else 500
    return jsonify(result), status_code


@bp.delete("/api/apktool/projects/<project>")
@auth.login_required
@auth.csrf_protect
def delete_project(project):
    result, err = _wrap(apktool_manager.delete_project, project)
    if err:
        return err
    auth.audit_log("apktool_project_delete", {"project": project})
    return jsonify(result)
