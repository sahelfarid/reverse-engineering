import json
from unittest.mock import patch

from adb import manager as adb_manager


def _post(auth_client, url, payload=None):
    return auth_client.post(
        url,
        data=json.dumps(payload if payload is not None else {}),
        content_type="application/json",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )


def test_status_success(auth_client):
    with patch("routes.jadx.jadx_manager.get_status", return_value={"ok": True}):
        res = auth_client.get("/api/jadx/status")
    assert res.status_code == 200


def test_install_success_and_audit_log(auth_client):
    fake_status = {"jadx": {"version": "1.5.1"}}
    with patch("routes.jadx.jadx_manager.ensure_jadx", return_value="/opt/jadx/bin/jadx"), \
         patch("routes.jadx.jadx_manager.get_status", return_value=fake_status), \
         patch("routes.jadx.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/jadx/install")
    assert res.status_code == 200
    assert res.get_json()["status"] == fake_status
    mock_audit.assert_called_once_with("jadx_install", {"path": "/opt/jadx/bin/jadx", "version": "1.5.1"})


def test_install_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    assert client.post("/api/jadx/install").status_code == 403


def test_decompile_starts_background_job_and_audit_logs(auth_client):
    with patch("routes.jadx.adb_jobs.create_job", return_value="job-1") as mock_create, \
         patch("routes.jadx.adb_jobs.run_in_background") as mock_run, \
         patch("routes.jadx.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/jadx/decompile/com.example.app", {"no_res": True})
    assert res.status_code == 200
    assert res.get_json()["job_id"] == "job-1"
    mock_create.assert_called_once_with("jadx_decompile", label="com.example.app")
    mock_run.assert_called_once()
    mock_audit.assert_called_once()


def test_import_rejects_missing_file(auth_client):
    res = auth_client.post(
        "/api/jadx/import", data={}, content_type="multipart/form-data",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_file"


def test_import_rejects_oversized_upload(auth_client):
    with patch("routes.jadx.config.load_settings", return_value={"max_upload_mb": 0}):
        res = auth_client.post(
            "/api/jadx/import",
            data={"file": (__import__("io").BytesIO(b"x" * 2000), "sample.apk")},
            content_type="multipart/form-data",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 413


def test_import_rejects_bad_extension_before_backgrounding(auth_client):
    with patch("routes.jadx.jadx_manager.save_uploaded_artifact", side_effect=adb_manager.AdbError("bad ext")):
        res = auth_client.post(
            "/api/jadx/import",
            data={"file": (__import__("io").BytesIO(b"x"), "payload.exe")},
            content_type="multipart/form-data",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 400


def test_import_starts_background_job_and_audit_logs(auth_client, tmp_path):
    apk_path = tmp_path / "sample.apk"
    apk_path.write_bytes(b"fake")
    with patch("routes.jadx.jadx_manager.save_uploaded_artifact", return_value=("proj-1", apk_path)), \
         patch("routes.jadx.adb_jobs.create_job", return_value="job-2") as mock_create, \
         patch("routes.jadx.adb_jobs.run_in_background") as mock_run, \
         patch("routes.jadx.auth.audit_log") as mock_audit:
        res = auth_client.post(
            "/api/jadx/import",
            data={"file": (__import__("io").BytesIO(b"x"), "sample.apk")},
            content_type="multipart/form-data",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    body = res.get_json()
    assert body["job_id"] == "job-2"
    assert body["project"] == "proj-1"
    mock_create.assert_called_once_with("jadx_import", label="proj-1")
    mock_run.assert_called_once()
    mock_audit.assert_called_once()


def test_import_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    res = client.post(
        "/api/jadx/import",
        data={"file": (__import__("io").BytesIO(b"x"), "sample.apk")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 403


def test_projects_success(auth_client):
    with patch("routes.jadx.jadx_manager.list_projects", return_value=[{"project": "com.example.app"}]):
        res = auth_client.get("/api/jadx/projects")
    assert res.status_code == 200
    assert res.get_json()["projects"] == [{"project": "com.example.app"}]


def test_browse_maps_adb_error(auth_client):
    with patch("routes.jadx.jadx_manager.browse_project", side_effect=adb_manager.AdbError("bad path")):
        res = auth_client.get("/api/jadx/projects/com.example.app/browse?path=../x")
    assert res.status_code == 400


def test_read_file_success(auth_client):
    with patch("routes.jadx.jadx_manager.read_project_file", return_value="content"):
        res = auth_client.get("/api/jadx/projects/com.example.app/file?path=Hello.java")
    assert res.status_code == 200
    assert res.get_json()["content"] == "content"


def test_read_file_requires_path(auth_client):
    res = auth_client.get("/api/jadx/projects/com.example.app/file")
    assert res.status_code == 400


def test_no_write_route_on_file(auth_client):
    """Locks in the read-only contract: jadx output is never edited/rebuilt,
    unlike the apktool tab's editor."""
    res = auth_client.post(
        "/api/jadx/projects/com.example.app/file?path=Hello.java",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )
    assert res.status_code == 405


def test_search_requires_query(auth_client):
    res = auth_client.get("/api/jadx/projects/com.example.app/search")
    assert res.status_code == 400


def test_search_success(auth_client):
    with patch("routes.jadx.jadx_manager.search_project", return_value=[{"path": "A.java", "line": 1, "snippet": "x"}]) as mock_search:
        res = auth_client.get("/api/jadx/projects/com.example.app/search?q=needle&regex=1&ignore_case=0&max_results=999")
    assert res.status_code == 200
    assert res.get_json()["results"][0]["path"] == "A.java"
    mock_search.assert_called_once_with(
        "com.example.app", "needle", max_results=500, ignore_case=False, regex=True,
    )


def test_manifest_success_and_error(auth_client):
    with patch("routes.jadx.jadx_manager.manifest_summary", return_value={"ok": True, "package": "com.example.app"}):
        res = auth_client.get("/api/jadx/projects/com.example.app/manifest")
    assert res.status_code == 200

    with patch("routes.jadx.jadx_manager.manifest_summary", side_effect=adb_manager.AdbError("no manifest")):
        res = auth_client.get("/api/jadx/projects/com.example.app/manifest")
    assert res.status_code == 400


def test_findings_get_not_run_returns_404(auth_client):
    with patch("routes.jadx.jadx_manager.validate_project", return_value="com.example.app"), \
         patch("routes.jadx.jadx_manager.get_findings", return_value=None):
        res = auth_client.get("/api/jadx/projects/com.example.app/findings")
    assert res.status_code == 404


def test_findings_get_returns_persisted_results(auth_client):
    with patch("routes.jadx.jadx_manager.validate_project", return_value="com.example.app"), \
         patch("routes.jadx.jadx_manager.get_findings", return_value=[{"id": "x"}]):
        res = auth_client.get("/api/jadx/projects/com.example.app/findings")
    assert res.status_code == 200
    assert res.get_json()["findings"] == [{"id": "x"}]


def test_findings_get_rejects_invalid_project(auth_client):
    with patch("routes.jadx.jadx_manager.validate_project", side_effect=adb_manager.AdbError("invalid project name")):
        res = auth_client.get("/api/jadx/projects/../etc/findings")
    assert res.status_code in (400, 404)


def test_run_findings_success_and_audit_log(auth_client):
    with patch("routes.jadx.jadx_manager.run_static_checks", return_value=[{"id": "x"}, {"id": "y"}]), \
         patch("routes.jadx.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/jadx/projects/com.example.app/findings")
    assert res.status_code == 200
    assert len(res.get_json()["findings"]) == 2
    mock_audit.assert_called_once_with("jadx_findings_run", {"project": "com.example.app", "count": 2})


def test_run_findings_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    assert client.post("/api/jadx/projects/com.example.app/findings").status_code == 403


def test_report_invalid_format_rejected(auth_client):
    res = auth_client.get("/api/jadx/projects/com.example.app/report?format=exe")
    assert res.status_code == 400


def test_report_success(auth_client, tmp_path):
    report_path = tmp_path / "report.json"
    report_path.write_text("{}", encoding="utf-8")
    with patch("routes.jadx.jadx_manager.export_report", return_value=report_path):
        res = auth_client.get("/api/jadx/projects/com.example.app/report?format=json")
    assert res.status_code == 200


def test_delete_project_success_and_audit_log(auth_client):
    with patch("routes.jadx.jadx_manager.delete_project", return_value={"ok": True}), \
         patch("routes.jadx.auth.audit_log") as mock_audit:
        res = auth_client.delete(
            "/api/jadx/projects/com.example.app",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    mock_audit.assert_called_once_with("jadx_project_delete", {"project": "com.example.app"})


def test_delete_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    assert client.delete("/api/jadx/projects/com.example.app").status_code == 403


def test_routes_require_login(client):
    assert client.get("/api/jadx/status").status_code == 401
    assert client.get("/api/jadx/projects").status_code == 401
    assert client.get("/api/jadx/projects/com.example.app/manifest").status_code == 401
    assert client.get("/api/jadx/projects/com.example.app/findings").status_code == 401
