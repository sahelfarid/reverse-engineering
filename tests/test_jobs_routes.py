import json
from unittest.mock import patch


def test_list_jobs_success(auth_client):
    with patch("routes.jobs.adb_jobs.list_jobs", return_value=[{"id": "j1"}]):
        res = auth_client.get("/api/jobs")
    assert res.status_code == 200
    assert res.get_json()["jobs"] == [{"id": "j1"}]


def test_get_job_not_found(auth_client):
    with patch("routes.jobs.adb_jobs.get_job", return_value=None):
        res = auth_client.get("/api/jobs/does-not-exist")
    assert res.status_code == 404


def test_get_job_success(auth_client):
    with patch("routes.jobs.adb_jobs.get_job", return_value={"id": "j1", "status": "running"}):
        res = auth_client.get("/api/jobs/j1")
    assert res.status_code == 200


def test_cancel_job_success(auth_client):
    with patch("routes.jobs.adb_jobs.cancel_job", return_value=True):
        res = auth_client.post("/api/jobs/j1/cancel", headers={"X-CSRF-Token": auth_client.csrf_token})
    assert res.status_code == 200
    assert res.get_json()["ok"] is True


def test_cancel_job_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    res = client.post("/api/jobs/j1/cancel")
    assert res.status_code == 403


def test_download_not_ready_when_job_missing(auth_client):
    with patch("routes.jobs.adb_jobs.get_job", return_value=None):
        res = auth_client.get("/api/jobs/j1/download")
    assert res.status_code == 400
    assert res.get_json()["error"] == "not_ready"


def test_download_not_ready_when_job_not_done(auth_client):
    with patch("routes.jobs.adb_jobs.get_job", return_value={"status": "running", "result": None}):
        res = auth_client.get("/api/jobs/j1/download")
    assert res.status_code == 400


def test_download_returns_structured_error_for_stale_file(auth_client):
    # The bug fixed in this pass: a done job whose result file was already
    # cleaned up used to fall through to send_file() and surface a raw
    # werkzeug 404 page instead of a clean JSON error.
    with patch("routes.jobs.adb_jobs.get_job", return_value={
        "status": "done", "result": {"file_path": "/nonexistent/path/to/file.zip", "download_name": "file.zip"},
    }):
        res = auth_client.get("/api/jobs/j1/download")
    assert res.status_code == 410
    assert res.get_json()["error"] == "result_file_missing"


def test_download_success_cleans_up_temp_dir(auth_client, tmp_path):
    result_file = tmp_path / "bundle.zip"
    result_file.write_bytes(b"PK\x03\x04")
    with patch("routes.jobs.adb_jobs.get_job", return_value={
        "status": "done",
        "result": {"file_path": str(result_file), "download_name": "bundle.zip", "tmp_dir": str(tmp_path)},
    }), patch("routes.jobs.shutil.rmtree") as mock_rmtree:
        res = auth_client.get("/api/jobs/j1/download")
        assert res.status_code == 200
        res.close()  # must happen while shutil.rmtree is still patched
        mock_rmtree.assert_called_once_with(str(tmp_path), ignore_errors=True)


def test_download_success_without_tmp_dir_skips_cleanup(auth_client, tmp_path):
    result_file = tmp_path / "app.apk"
    result_file.write_bytes(b"apk-bytes")
    with patch("routes.jobs.adb_jobs.get_job", return_value={
        "status": "done", "result": {"file_path": str(result_file), "download_name": "app.apk"},
    }), patch("routes.jobs.shutil.rmtree") as mock_rmtree:
        res = auth_client.get("/api/jobs/j1/download")
        assert res.status_code == 200
        res.close()
    mock_rmtree.assert_not_called()


def test_jobs_routes_require_login(client):
    assert client.get("/api/jobs").status_code == 401
    assert client.get("/api/jobs/j1").status_code == 401
    assert client.get("/api/jobs/j1/download").status_code == 401
