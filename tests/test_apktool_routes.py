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
    with patch("routes.apktool.apktool_manager.get_status", return_value={"ok": True}):
        res = auth_client.get("/api/apktool/status")
    assert res.status_code == 200


def test_install_success_and_audit_log(auth_client, tmp_path):
    jar = tmp_path / "apktool.jar"
    jar.write_bytes(b"jar")
    fake_status = {"apktool": {"version": "3.0.2"}}
    with patch("routes.apktool.apktool_manager.ensure_apktool", return_value=jar), \
         patch("routes.apktool.apktool_manager.get_status", return_value=fake_status), \
         patch("routes.apktool.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/apktool/install")
    assert res.status_code == 200
    assert res.get_json()["status"] == fake_status
    mock_audit.assert_called_once_with("apktool_install", {"path": str(jar), "version": "3.0.2"})


def test_install_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    assert client.post("/api/apktool/install").status_code == 403


def test_decompile_starts_background_job_and_audit_logs(auth_client):
    with patch("routes.apktool.adb_jobs.create_job", return_value="job-1") as mock_create, \
         patch("routes.apktool.adb_jobs.run_in_background") as mock_run, \
         patch("routes.apktool.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/apktool/decompile/com.example.app")
    assert res.status_code == 200
    assert res.get_json()["job_id"] == "job-1"
    mock_create.assert_called_once_with("apktool_decompile", label="com.example.app")
    mock_run.assert_called_once()
    mock_audit.assert_called_once()


def test_projects_success(auth_client):
    with patch("routes.apktool.apktool_manager.list_projects", return_value=[{"project": "com.example.app"}]):
        res = auth_client.get("/api/apktool/projects")
    assert res.status_code == 200
    assert res.get_json()["projects"] == [{"project": "com.example.app"}]


def test_browse_maps_adb_error(auth_client):
    with patch("routes.apktool.apktool_manager.browse_project", side_effect=adb_manager.AdbError("bad path")):
        res = auth_client.get("/api/apktool/projects/com.example.app/browse?path=../x")
    assert res.status_code == 400


def test_read_file_success(auth_client):
    with patch("routes.apktool.apktool_manager.read_project_file", return_value="content"):
        res = auth_client.get("/api/apktool/projects/com.example.app/file?path=AndroidManifest.xml")
    assert res.status_code == 200
    assert res.get_json()["content"] == "content"


def test_write_file_success_and_audit_log(auth_client):
    with patch("routes.apktool.apktool_manager.write_project_file", return_value={"ok": True}), \
         patch("routes.apktool.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/apktool/projects/com.example.app/file?path=AndroidManifest.xml", {"content": "x"})
    assert res.status_code == 200
    mock_audit.assert_called_once_with("apktool_file_save", {"project": "com.example.app", "path": "AndroidManifest.xml"})


def test_write_file_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    res = client.post("/api/apktool/projects/com.example.app/file?path=x")
    assert res.status_code == 403


def test_rebuild_starts_background_job(auth_client):
    with patch("routes.apktool.adb_jobs.create_job", return_value="job-2"), \
         patch("routes.apktool.adb_jobs.run_in_background") as mock_run, \
         patch("routes.apktool.auth.audit_log"):
        res = _post(auth_client, "/api/apktool/projects/com.example.app/rebuild")
    assert res.status_code == 200
    assert res.get_json()["job_id"] == "job-2"
    mock_run.assert_called_once()


def test_reinstall_success_and_audit_log(auth_client):
    with patch("routes.apktool.apktool_manager.validate_project", return_value="com.example.app"), \
         patch("routes.apktool.apktool_manager.reinstall", return_value={"ok": True, "output": "Success"}), \
         patch("routes.apktool.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/apktool/projects/com.example.app/reinstall")
    assert res.status_code == 200
    mock_audit.assert_called_once_with("apktool_reinstall", {"serial": "s1", "project": "com.example.app"})


def test_delete_project_success_and_audit_log(auth_client):
    with patch("routes.apktool.apktool_manager.delete_project", return_value={"ok": True}), \
         patch("routes.apktool.auth.audit_log") as mock_audit:
        res = auth_client.delete(
            "/api/apktool/projects/com.example.app",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    mock_audit.assert_called_once_with("apktool_project_delete", {"project": "com.example.app"})


def test_routes_require_login(client):
    assert client.get("/api/apktool/status").status_code == 401
    assert client.get("/api/apktool/projects").status_code == 401
