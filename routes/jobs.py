import shutil

from flask import Blueprint, jsonify, send_file

import auth
from adb import jobs as adb_jobs

bp = Blueprint("jobs", __name__)


@bp.get("/api/jobs")
@auth.login_required
def list_jobs():
    return jsonify({"ok": True, "jobs": adb_jobs.list_jobs()})


@bp.get("/api/jobs/<job_id>")
@auth.login_required
def get_job(job_id):
    job = adb_jobs.get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({"ok": True, "job": job})


@bp.post("/api/jobs/<job_id>/cancel")
@auth.login_required
@auth.csrf_protect
def cancel_job(job_id):
    ok = adb_jobs.cancel_job(job_id)
    return jsonify({"ok": ok})


@bp.get("/api/jobs/<job_id>/download")
@auth.login_required
def download_job_result(job_id):
    job = adb_jobs.get_job(job_id)
    if not job or job["status"] != "done" or not job.get("result") or not job["result"].get("file_path"):
        return jsonify({"ok": False, "error": "not_ready"}), 400
    result = job["result"]
    response = send_file(result["file_path"], as_attachment=True, download_name=result.get("download_name"))
    tmp_dir = result.get("tmp_dir")
    if tmp_dir:
        @response.call_on_close
        def _cleanup():
            shutil.rmtree(tmp_dir, ignore_errors=True)
    return response
