from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adb import manager as adb_manager


def test_targets_success(auth_client):
    res = auth_client.get("/api/backup/targets")
    assert res.status_code == 200
    assert "photos" in res.get_json()["targets"]


def test_export_folder_unknown_target(auth_client):
    res = auth_client.get("/api/devices/s1/backup/export/not_a_target")
    assert res.status_code == 404


def test_export_folder_success_cleans_up(auth_client, tmp_path):
    zip_path = tmp_path / "bundle.zip"
    zip_path.write_bytes(b"PK\x03\x04")
    with patch("routes.backup.tempfile.mkdtemp", return_value=str(tmp_path)), \
         patch("routes.backup.adb_manager.run", return_value=MagicMock(returncode=0, stderr="")), \
         patch("routes.backup.adb_files.zip_folder", return_value=zip_path), \
         patch("routes.backup.shutil.rmtree") as mock_rmtree, \
         patch("routes.backup.auth.audit_log") as mock_audit:
        res = auth_client.get("/api/devices/s1/backup/export/photos")
        assert res.status_code == 200
        res.close()  # must happen while shutil.rmtree is still patched
        mock_rmtree.assert_called_once_with(str(tmp_path), ignore_errors=True)
    mock_audit.assert_called_once_with("backup_export_folder", {"serial": "s1", "target": "photos"})


def test_export_folder_maps_pull_failure(auth_client, tmp_path):
    with patch("routes.backup.tempfile.mkdtemp", return_value=str(tmp_path)), \
         patch("routes.backup.adb_manager.run", return_value=MagicMock(returncode=1, stderr="pull failed")):
        res = auth_client.get("/api/devices/s1/backup/export/photos")
    assert res.status_code == 400


def test_export_logcat_success_cleans_up(auth_client, tmp_path):
    log_file = tmp_path / "logcat-s1.txt"
    log_file.write_text("log contents")
    with patch("routes.backup.tempfile.mkdtemp", return_value=str(tmp_path)), \
         patch("routes.backup.adb_backup.dump_logcat_to_file", return_value=log_file), \
         patch("routes.backup.shutil.rmtree") as mock_rmtree, \
         patch("routes.backup.auth.audit_log") as mock_audit:
        res = auth_client.get("/api/devices/s1/backup/logcat")
        assert res.status_code == 200
        res.close()  # must happen while shutil.rmtree is still patched
        mock_rmtree.assert_called_once_with(str(tmp_path), ignore_errors=True)
    mock_audit.assert_called_once_with("backup_export_logcat", {"serial": "s1"})


def test_export_apk_success_cleans_up(auth_client, tmp_path):
    apk_file = tmp_path / "com.example.app.apk"
    apk_file.write_bytes(b"apk-bytes")
    with patch("routes.backup.tempfile.mkdtemp", return_value=str(tmp_path)), \
         patch("routes.backup.adb_packages.pull_apk", return_value=apk_file), \
         patch("routes.backup.shutil.rmtree") as mock_rmtree, \
         patch("routes.backup.auth.audit_log") as mock_audit:
        res = auth_client.get("/api/devices/s1/backup/apk/com.example.app")
        assert res.status_code == 200
        res.close()  # must happen while shutil.rmtree is still patched
        mock_rmtree.assert_called_once_with(str(tmp_path), ignore_errors=True)
    mock_audit.assert_called_once_with("backup_export_apk", {"serial": "s1", "package": "com.example.app"})


def test_export_database_missing_fields(auth_client):
    res = auth_client.get("/api/devices/s1/backup/database?package=com.example.app")
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_fields"


def test_export_database_success(auth_client, tmp_path):
    db_file = tmp_path / "app.db"
    db_file.write_bytes(b"db-bytes")
    with patch("routes.backup.tempfile.mkdtemp", return_value=str(tmp_path)), \
         patch("routes.backup.adb_backup.export_database", return_value=db_file), \
         patch("routes.backup.shutil.rmtree") as mock_rmtree, \
         patch("routes.backup.auth.audit_log") as mock_audit:
        res = auth_client.get("/api/devices/s1/backup/database?package=com.example.app&db=app.db")
        assert res.status_code == 200
        res.close()  # must happen while shutil.rmtree is still patched
        mock_rmtree.assert_called_once_with(str(tmp_path), ignore_errors=True)
    mock_audit.assert_called_once_with(
        "backup_export_database", {"serial": "s1", "package": "com.example.app", "db": "app.db"}
    )


def test_export_app_data_missing_package(auth_client):
    res = auth_client.get("/api/devices/s1/backup/app-data")
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_package"


def test_export_app_data_success_and_maps_adb_error(auth_client, tmp_path):
    tar_file = tmp_path / "com.example.app_data.tar.gz"
    tar_file.write_bytes(b"tar-bytes")
    with patch("routes.backup.tempfile.mkdtemp", return_value=str(tmp_path)), \
         patch("routes.backup.adb_backup.export_app_data", return_value=tar_file), \
         patch("routes.backup.shutil.rmtree") as mock_rmtree, \
         patch("routes.backup.auth.audit_log"):
        res = auth_client.get("/api/devices/s1/backup/app-data?package=com.example.app")
        assert res.status_code == 200
        res.close()  # must happen while shutil.rmtree is still patched
        mock_rmtree.assert_called_once_with(str(tmp_path), ignore_errors=True)

    with patch("routes.backup.tempfile.mkdtemp", return_value=str(tmp_path)), \
         patch("routes.backup.adb_backup.export_app_data", side_effect=adb_manager.AdbError("root tar failed")):
        res = auth_client.get("/api/devices/s1/backup/app-data?package=com.example.app")
    assert res.status_code == 400


def test_export_app_data_async_creates_job(auth_client):
    with patch("routes.backup.adb_jobs.create_job", return_value="job-1") as mock_create, \
         patch("routes.backup.adb_jobs.run_in_background") as mock_run, \
         patch("routes.backup.auth.audit_log") as mock_audit:
        res = auth_client.get("/api/devices/s1/backup/app-data/async?package=com.example.app")
    assert res.status_code == 200
    assert res.get_json()["job_id"] == "job-1"
    mock_create.assert_called_once()
    mock_run.assert_called_once()
    mock_audit.assert_called_once_with("backup_export_app_data_async", {"serial": "s1", "package": "com.example.app"})


def test_export_app_data_async_missing_package(auth_client):
    res = auth_client.get("/api/devices/s1/backup/app-data/async")
    assert res.status_code == 400


def test_export_app_data_async_run_closure_success(auth_client, tmp_path):
    tar_file = tmp_path / "com.example.app_data.tar.gz"
    tar_file.write_bytes(b"tar-bytes")
    with patch("routes.backup.adb_jobs.create_job", return_value="job-1"), \
         patch("routes.backup.adb_jobs.run_in_background") as mock_run, \
         patch("routes.backup.tempfile.mkdtemp", return_value=str(tmp_path)), \
         patch("routes.backup.auth.audit_log"):
        res = auth_client.get("/api/devices/s1/backup/app-data/async?package=com.example.app")
    assert res.status_code == 200
    run_closure = mock_run.call_args[0][1]

    with patch("routes.backup.adb_backup.export_app_data", return_value=tar_file) as mock_export:
        result = run_closure("job-1")

    mock_export.assert_called_once_with("s1", "com.example.app", Path(tmp_path))
    assert result == {
        "file_path": str(tar_file), "download_name": "com.example.app_data.tar.gz", "tmp_dir": str(tmp_path),
    }
    assert tmp_path.exists()  # success path leaves cleanup to the download route


def test_export_app_data_async_run_closure_cleans_up_on_failure(auth_client, tmp_path):
    with patch("routes.backup.adb_jobs.create_job", return_value="job-2"), \
         patch("routes.backup.adb_jobs.run_in_background") as mock_run, \
         patch("routes.backup.tempfile.mkdtemp", return_value=str(tmp_path)), \
         patch("routes.backup.auth.audit_log"):
        res = auth_client.get("/api/devices/s1/backup/app-data/async?package=com.example.app")
    assert res.status_code == 200
    run_closure = mock_run.call_args[0][1]

    with patch("routes.backup.adb_backup.export_app_data", side_effect=adb_manager.AdbError("no root, no run-as")), \
         patch("routes.backup.shutil.rmtree") as mock_rmtree:
        with pytest.raises(adb_manager.AdbError):
            run_closure("job-2")

    mock_rmtree.assert_called_once_with(str(tmp_path), ignore_errors=True)


def test_all_export_routes_require_login(client):
    assert client.get("/api/backup/targets").status_code == 401
    assert client.get("/api/devices/s1/backup/export/photos").status_code == 401
    assert client.get("/api/devices/s1/backup/logcat").status_code == 401
