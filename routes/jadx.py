from flask import Blueprint, jsonify, request, send_file

import auth
import config
from adb import jadx_manager
from adb import jobs as adb_jobs
from adb import manager as adb_manager

bp = Blueprint("jadx", __name__)


def _wrap(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except adb_manager.AdbNotInstalledError:
        return None, (jsonify({"ok": False, "error": "adb_not_installed"}), 503)
    except adb_manager.AdbError as exc:
        return None, (jsonify({"ok": False, "error": str(exc)}), 400)


@bp.get("/api/jadx/status")
@auth.login_required
def status():
    return jsonify(jadx_manager.get_status())


@bp.post("/api/jadx/install")
@auth.login_required
@auth.csrf_protect
def install_jadx():
    launcher, err = _wrap(jadx_manager.ensure_jadx)
    if err:
        return err
    status_data = jadx_manager.get_status()
    auth.audit_log("jadx_install", {"path": str(launcher), "version": status_data["jadx"].get("version")})
    return jsonify({"ok": True, "status": status_data})


@bp.post("/api/devices/<serial>/jadx/decompile/<package>")
@auth.login_required
@auth.csrf_protect
def decompile(serial, package):
    data = request.get_json(silent=True) or {}
    no_res = bool(data.get("no_res"))
    deobf = bool(data.get("deobf"))
    job_id = adb_jobs.create_job("jadx_decompile", label=package)

    def _run(job_id):
        path = jadx_manager.decompile(serial, package, job_id=job_id, no_res=no_res, deobf=deobf)
        return {"project": package, "path": str(path)}

    adb_jobs.run_in_background(job_id, _run)
    auth.audit_log("jadx_decompile", {"serial": serial, "package": package, "job_id": job_id})
    return jsonify({"ok": True, "job_id": job_id})


@bp.post("/api/jadx/import")
@auth.login_required
@auth.csrf_protect
def import_artifact():
    """Local-upload path: analyze an APK/DEX/JAR the operator already has on
    disk instead of pulling one off a device. The file is validated and saved
    synchronously here (a Flask FileStorage isn't safe to touch from a
    background thread once this request ends); only the slow jadx run itself
    happens in the background job."""
    settings = config.load_settings()
    max_bytes = int(settings.get("max_upload_mb", 200)) * 1024 * 1024
    if request.content_length and request.content_length > max_bytes:
        return jsonify({"ok": False, "error": "file_too_large"}), 413

    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"ok": False, "error": "missing_file"}), 400

    project_name = request.form.get("project") or None
    no_res = request.form.get("no_res") in ("1", "true", "True")
    deobf = request.form.get("deobf") in ("1", "true", "True")

    try:
        project, apk_path = jadx_manager.save_uploaded_artifact(uploaded, project_name)
    except adb_manager.AdbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    job_id = adb_jobs.create_job("jadx_import", label=project)

    def _run(job_id):
        path = jadx_manager.decompile_uploaded(project, apk_path, job_id=job_id, no_res=no_res, deobf=deobf)
        return {"project": project, "path": str(path)}

    adb_jobs.run_in_background(job_id, _run)
    auth.audit_log("jadx_import", {"project": project, "job_id": job_id})
    return jsonify({"ok": True, "job_id": job_id, "project": project})


@bp.get("/api/jadx/projects")
@auth.login_required
def projects():
    result, err = _wrap(jadx_manager.list_projects)
    return err or jsonify({"ok": True, "projects": result})


@bp.get("/api/jadx/projects/<project>/browse")
@auth.login_required
def browse(project):
    path = request.args.get("path", "")
    result, err = _wrap(jadx_manager.browse_project, project, path)
    return err or jsonify(result)


@bp.get("/api/jadx/projects/<project>/file")
@auth.login_required
def read_file(project):
    """Read only -- there is deliberately no POST/write route here. jadx
    output is not edited or rebuilt (that's the apktool module's job)."""
    path = request.args.get("path", "")
    if not path:
        return jsonify({"ok": False, "error": "missing_path"}), 400
    content, err = _wrap(jadx_manager.read_project_file, project, path)
    return err or jsonify({"ok": True, "path": path, "content": content})


@bp.get("/api/jadx/projects/<project>/search")
@auth.login_required
def search(project):
    query = request.args.get("q", "")
    if not query:
        return jsonify({"ok": False, "error": "missing_query"}), 400
    regex = request.args.get("regex") in ("1", "true", "True")
    ignore_case = request.args.get("ignore_case", "1") not in ("0", "false", "False")
    try:
        max_results = min(int(request.args.get("max_results", 200)), 500)
    except ValueError:
        max_results = 200
    result, err = _wrap(
        jadx_manager.search_project, project, query,
        max_results=max_results, ignore_case=ignore_case, regex=regex,
    )
    return err or jsonify({"ok": True, "results": result})


@bp.get("/api/jadx/projects/<project>/manifest")
@auth.login_required
def manifest(project):
    result, err = _wrap(jadx_manager.manifest_summary, project)
    return err or jsonify(result)


@bp.get("/api/jadx/projects/<project>/findings")
@auth.login_required
def get_findings(project):
    try:
        jadx_manager.validate_project(project)
    except adb_manager.AdbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    findings = jadx_manager.get_findings(project)
    if findings is None:
        return jsonify({"ok": False, "error": "not_run"}), 404
    return jsonify({"ok": True, "findings": findings})


@bp.post("/api/jadx/projects/<project>/findings")
@auth.login_required
@auth.csrf_protect
def run_findings(project):
    findings, err = _wrap(jadx_manager.run_static_checks, project)
    if err:
        return err
    auth.audit_log("jadx_findings_run", {"project": project, "count": len(findings)})
    return jsonify({"ok": True, "findings": findings})


@bp.get("/api/jadx/projects/<project>/report")
@auth.login_required
def report(project):
    fmt = request.args.get("format", "json")
    if fmt not in ("json", "md"):
        return jsonify({"ok": False, "error": "invalid_format"}), 400
    path, err = _wrap(jadx_manager.export_report, project, fmt)
    if err:
        return err
    return send_file(path, as_attachment=True, download_name=path.name)


@bp.delete("/api/jadx/projects/<project>")
@auth.login_required
@auth.csrf_protect
def delete_project(project):
    result, err = _wrap(jadx_manager.delete_project, project)
    if err:
        return err
    auth.audit_log("jadx_project_delete", {"project": project})
    return jsonify(result)
