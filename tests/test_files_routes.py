import io
import json
from unittest.mock import MagicMock, patch

from adb import manager as adb_manager


def _post(auth_client, url, payload):
    return auth_client.post(
        url, data=json.dumps(payload), content_type="application/json",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )


def test_browse_success(auth_client):
    with patch("routes.files.adb_files.list_directory", return_value={"ok": True, "entries": []}):
        res = auth_client.get("/api/devices/s1/files/browse?path=/sdcard")
    assert res.status_code == 200


def test_browse_not_ok_result_is_404(auth_client):
    with patch("routes.files.adb_files.list_directory", return_value={"ok": False, "error": "not_found"}):
        res = auth_client.get("/api/devices/s1/files/browse?path=/nope")
    assert res.status_code == 404


def test_browse_maps_adb_not_installed(auth_client):
    with patch("routes.files.adb_files.list_directory", side_effect=adb_manager.AdbNotInstalledError("x")):
        res = auth_client.get("/api/devices/s1/files/browse")
    assert res.status_code == 503


def test_search_missing_query(auth_client):
    res = auth_client.get("/api/devices/s1/files/search?path=/sdcard")
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_query"


def test_search_success(auth_client):
    with patch("routes.files.adb_files.search_path", return_value={"ok": True, "results": []}):
        res = auth_client.get("/api/devices/s1/files/search?path=/sdcard&query=txt")
    assert res.status_code == 200


def test_mkdir_missing_path(auth_client):
    res = _post(auth_client, "/api/devices/s1/files/mkdir", {})
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_path"


def test_mkdir_success_and_audit_log(auth_client):
    with patch("routes.files.adb_files.mkdir_path", return_value={"ok": True, "error": None}), \
         patch("routes.files.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/files/mkdir", {"path": "/sdcard/new"})
    assert res.status_code == 200
    mock_audit.assert_called_once_with("file_mkdir", {"serial": "s1", "path": "/sdcard/new"})


def test_mkdir_maps_adb_error(auth_client):
    with patch("routes.files.adb_files.mkdir_path", side_effect=adb_manager.AdbError("boom")):
        res = _post(auth_client, "/api/devices/s1/files/mkdir", {"path": "/sdcard/new"})
    assert res.status_code == 400


def test_delete_missing_path(auth_client):
    res = _post(auth_client, "/api/devices/s1/files/delete", {})
    assert res.status_code == 400


def test_delete_success_passes_recursive_flag(auth_client):
    with patch("routes.files.adb_files.delete_path", return_value={"ok": True, "error": None}) as mock_delete:
        res = _post(auth_client, "/api/devices/s1/files/delete", {"path": "/sdcard/x", "recursive": True})
    assert res.status_code == 200
    mock_delete.assert_called_once_with("s1", "/sdcard/x", True)


def test_rename_missing_fields(auth_client):
    res = _post(auth_client, "/api/devices/s1/files/rename", {"path": "/sdcard/x"})
    assert res.status_code == 400


def test_rename_success(auth_client):
    with patch("routes.files.adb_files.rename_path", return_value={"ok": True, "error": None}):
        res = _post(auth_client, "/api/devices/s1/files/rename", {"path": "/sdcard/x", "new_name": "y"})
    assert res.status_code == 200


def test_move_missing_fields(auth_client):
    res = _post(auth_client, "/api/devices/s1/files/move", {"src": "/a"})
    assert res.status_code == 400


def test_move_success(auth_client):
    with patch("routes.files.adb_files.move_path", return_value={"ok": True, "error": None}):
        res = _post(auth_client, "/api/devices/s1/files/move", {"src": "/a", "dest": "/b"})
    assert res.status_code == 200


def test_copy_missing_fields(auth_client):
    res = _post(auth_client, "/api/devices/s1/files/copy", {"src": "/a"})
    assert res.status_code == 400


def test_copy_success(auth_client):
    with patch("routes.files.adb_files.copy_path", return_value={"ok": True, "error": None}):
        res = _post(auth_client, "/api/devices/s1/files/copy", {"src": "/a", "dest": "/b"})
    assert res.status_code == 200


def test_upload_missing_file(auth_client):
    res = auth_client.post(
        "/api/devices/s1/files/upload",
        data={"remote_dir": "/sdcard"},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_file"


def test_upload_file_too_large(auth_client):
    # The werkzeug test client recomputes Content-Length from the real body,
    # so shrink the configured limit instead of trying to fake a huge upload.
    with patch("routes.files.config.load_settings", return_value={"max_upload_mb": 0}):
        data = {"file": (io.BytesIO(b"some bytes"), "big.bin")}
        res = auth_client.post(
            "/api/devices/s1/files/upload",
            data=data,
            content_type="multipart/form-data",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 413


def test_upload_success_and_audit_log(auth_client):
    with patch("routes.files.adb_files.push_file", return_value={"ok": True, "remote_path": "/sdcard/dest/a.txt"}), \
         patch("routes.files.auth.audit_log") as mock_audit:
        res = auth_client.post(
            "/api/devices/s1/files/upload",
            data={"file": (io.BytesIO(b"hello"), "a.txt"), "remote_dir": "/sdcard/dest"},
            content_type="multipart/form-data",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    assert res.get_json()["remote_path"] == "/sdcard/dest/a.txt"
    mock_audit.assert_called_once()


def test_preview_missing_path(auth_client):
    res = auth_client.get("/api/devices/s1/files/preview")
    assert res.status_code == 400


def test_preview_text_kind(auth_client):
    with patch("routes.files.adb_files.read_text_preview", return_value={"ok": True, "content": "hi", "truncated": False}):
        res = auth_client.get("/api/devices/s1/files/preview?path=/sdcard/a.txt")
    assert res.status_code == 200
    assert res.get_json()["kind"] == "text"


def test_preview_unsupported_kind(auth_client):
    res = auth_client.get("/api/devices/s1/files/preview?path=/sdcard/app.apk")
    assert res.status_code == 200
    assert res.get_json()["kind"] == "unsupported"


def test_preview_image_kind_pulls_and_cleans_up(auth_client, tmp_path):
    fake_image = tmp_path / "photo.png"
    fake_image.write_bytes(b"fake-png-bytes")
    with patch("routes.files.adb_files.pull_file", return_value=fake_image), \
         patch("routes.files.tempfile.mkdtemp", return_value=str(tmp_path)), \
         patch("routes.files.shutil.rmtree") as mock_rmtree:
        res = auth_client.get("/api/devices/s1/files/preview?path=/sdcard/photo.png")
        assert res.status_code == 200
        res.close()  # must happen while shutil.rmtree is still patched
        mock_rmtree.assert_called_once_with(str(tmp_path), ignore_errors=True)


def test_download_missing_path(auth_client):
    res = auth_client.get("/api/devices/s1/files/download")
    assert res.status_code == 400


def test_download_success_cleans_up_temp_dir(auth_client, tmp_path):
    fake_file = tmp_path / "a.txt"
    fake_file.write_text("data")
    with patch("routes.files.adb_files.pull_file", return_value=fake_file), \
         patch("routes.files.tempfile.mkdtemp", return_value=str(tmp_path)), \
         patch("routes.files.shutil.rmtree") as mock_rmtree, \
         patch("routes.files.auth.audit_log") as mock_audit:
        res = auth_client.get("/api/devices/s1/files/download?path=/sdcard/a.txt")
        assert res.status_code == 200
        res.close()  # must happen while shutil.rmtree is still patched
        mock_rmtree.assert_called_once_with(str(tmp_path), ignore_errors=True)
    mock_audit.assert_called_once_with("file_download", {"serial": "s1", "path": "/sdcard/a.txt"})


def test_download_folder_missing_path(auth_client):
    res = auth_client.get("/api/devices/s1/files/download-folder")
    assert res.status_code == 400


def test_download_folder_success_zips_and_cleans_up(auth_client, tmp_path):
    zip_path = tmp_path / "bundle.zip"
    zip_path.write_bytes(b"PK\x03\x04fake-zip")
    fake_proc = MagicMock(returncode=0, stderr="")
    with patch("routes.files.adb_manager.run", return_value=fake_proc), \
         patch("routes.files.tempfile.mkdtemp", return_value=str(tmp_path)), \
         patch("routes.files.adb_files.zip_folder", return_value=zip_path) as mock_zip, \
         patch("routes.files.shutil.rmtree") as mock_rmtree, \
         patch("routes.files.auth.audit_log") as mock_audit:
        res = auth_client.get("/api/devices/s1/files/download-folder?path=/sdcard/DCIM")
        assert res.status_code == 200
        res.close()  # must happen while shutil.rmtree is still patched
        mock_rmtree.assert_called_once_with(str(tmp_path), ignore_errors=True)
    mock_zip.assert_called_once()
    mock_audit.assert_called_once_with("file_download_folder", {"serial": "s1", "path": "/sdcard/DCIM"})


def test_download_folder_maps_pull_failure(auth_client, tmp_path):
    fake_proc = MagicMock(returncode=1, stderr="pull failed")
    with patch("routes.files.adb_manager.run", return_value=fake_proc), \
         patch("routes.files.tempfile.mkdtemp", return_value=str(tmp_path)):
        res = auth_client.get("/api/devices/s1/files/download-folder?path=/sdcard/DCIM")
    assert res.status_code == 400


def test_download_folder_async_creates_job(auth_client):
    with patch("routes.files.adb_jobs.create_job", return_value="job-123") as mock_create, \
         patch("routes.files.adb_jobs.run_in_background") as mock_run, \
         patch("routes.files.auth.audit_log") as mock_audit:
        res = auth_client.get("/api/devices/s1/files/download-folder/async?path=/sdcard/dir")
    assert res.status_code == 200
    assert res.get_json()["job_id"] == "job-123"
    mock_create.assert_called_once_with("folder_download", label="/sdcard/dir")
    mock_run.assert_called_once()
    mock_audit.assert_called_once()


def test_download_folder_async_missing_path(auth_client):
    res = auth_client.get("/api/devices/s1/files/download-folder/async")
    assert res.status_code == 400
