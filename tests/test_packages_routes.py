import io
import json
from unittest.mock import patch

from adb import manager as adb_manager


def _post(auth_client, url, payload=None):
    return auth_client.post(
        url, data=json.dumps(payload or {}), content_type="application/json",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )


def test_list_packages_success(auth_client):
    with patch("routes.packages.adb_packages.list_packages", return_value=[{"package": "com.example.app"}]):
        res = auth_client.get("/api/devices/s1/packages")
    assert res.status_code == 200
    assert res.get_json()["packages"] == [{"package": "com.example.app"}]


def test_list_packages_maps_adb_not_installed(auth_client):
    with patch("routes.packages.adb_packages.list_packages", side_effect=adb_manager.AdbNotInstalledError("x")):
        res = auth_client.get("/api/devices/s1/packages")
    assert res.status_code == 503


def test_package_size_not_found(auth_client):
    with patch("routes.packages.adb_packages.get_apk_path", return_value=None):
        res = auth_client.get("/api/devices/s1/packages/com.example.app/size")
    assert res.status_code == 404


def test_package_size_success(auth_client):
    with patch("routes.packages.adb_packages.get_apk_path", return_value="/data/app/x.apk"), \
         patch("routes.packages.adb_packages.get_apk_size", return_value=12345):
        res = auth_client.get("/api/devices/s1/packages/com.example.app/size")
    assert res.status_code == 200
    assert res.get_json()["size"] == 12345


def test_install_missing_apk(auth_client):
    res = auth_client.post(
        "/api/devices/s1/packages/install", data={}, content_type="multipart/form-data",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_apk"


def test_install_single_apk_success_and_audit_log(auth_client):
    with patch("routes.packages.adb_packages.install_apk", return_value={"ok": True, "output": "Success"}), \
         patch("routes.packages.auth.audit_log") as mock_audit:
        res = auth_client.post(
            "/api/devices/s1/packages/install",
            data={"apk": (io.BytesIO(b"apk-bytes"), "app.apk")},
            content_type="multipart/form-data",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    assert res.get_json()["ok"] is True
    mock_audit.assert_called_once()


def test_install_multiple_apks_uses_install_multiple(auth_client):
    with patch("routes.packages.adb_packages.install_multiple_apks", return_value={"ok": True, "output": ""}) as mock_multi:
        res = auth_client.post(
            "/api/devices/s1/packages/install",
            data={"apk": [(io.BytesIO(b"a"), "a.apk"), (io.BytesIO(b"b"), "b.apk")]},
            content_type="multipart/form-data",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    mock_multi.assert_called_once()


def test_install_failure_returns_500(auth_client):
    with patch("routes.packages.adb_packages.install_apk", return_value={"ok": False, "output": "Failure"}):
        res = auth_client.post(
            "/api/devices/s1/packages/install",
            data={"apk": (io.BytesIO(b"apk-bytes"), "app.apk")},
            content_type="multipart/form-data",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 500


def test_install_async_creates_job(auth_client):
    with patch("routes.packages.adb_jobs.create_job", return_value="job-1") as mock_create, \
         patch("routes.packages.adb_jobs.run_in_background") as mock_run, \
         patch("routes.packages.auth.audit_log") as mock_audit:
        res = auth_client.post(
            "/api/devices/s1/packages/install/async",
            data={"apk": (io.BytesIO(b"apk-bytes"), "app.apk")},
            content_type="multipart/form-data",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    assert res.get_json()["job_id"] == "job-1"
    mock_create.assert_called_once()
    mock_run.assert_called_once()
    mock_audit.assert_called_once()


def test_install_async_missing_apk(auth_client):
    res = auth_client.post(
        "/api/devices/s1/packages/install/async", data={}, content_type="multipart/form-data",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )
    assert res.status_code == 400


def test_uninstall_passes_keep_data(auth_client):
    with patch("routes.packages.adb_packages.uninstall_apk", return_value={"ok": True, "output": ""}) as mock_uninstall, \
         patch("routes.packages.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/packages/com.example.app/uninstall", {"keep_data": True})
    assert res.status_code == 200
    mock_uninstall.assert_called_once_with("s1", "com.example.app", True)
    mock_audit.assert_called_once_with(
        "package_uninstall", {"serial": "s1", "package": "com.example.app", "keep_data": True}
    )


def test_uninstall_maps_adb_error(auth_client):
    with patch("routes.packages.adb_packages.uninstall_apk", side_effect=adb_manager.AdbError("bad package")):
        res = _post(auth_client, "/api/devices/s1/packages/com.example.app/uninstall")
    assert res.status_code == 400


def test_action_routes_success_and_audit_log(auth_client):
    # _make_action_route() binds each action's backend function into a
    # closure at blueprint-registration (import) time, so patching
    # adb_packages.<fn> here wouldn't reach it -- patch one level down at
    # manager.shell instead, which every action ultimately calls through.
    for url_segment in ("disable", "enable", "clear-data", "force-stop", "launch"):
        with patch("routes.packages.adb_packages.manager.shell", return_value=("", "", 0)), \
             patch("routes.packages.auth.audit_log") as mock_audit:
            res = _post(auth_client, f"/api/devices/s1/packages/com.example.app/{url_segment}")
        assert res.status_code == 200, url_segment
        mock_audit.assert_called_once()


def test_action_route_maps_adb_error(auth_client):
    with patch("routes.packages.adb_packages.manager.shell", side_effect=adb_manager.AdbError("bad")):
        res = _post(auth_client, "/api/devices/s1/packages/com.example.app/disable")
    assert res.status_code == 400


def test_pull_apk_success_cleans_up_and_audit_logs(auth_client, tmp_path):
    apk_file = tmp_path / "com.example.app.apk"
    apk_file.write_bytes(b"apk-bytes")
    with patch("routes.packages.tempfile.mkdtemp", return_value=str(tmp_path)), \
         patch("routes.packages.adb_packages.pull_apk", return_value=apk_file), \
         patch("routes.packages.shutil.rmtree") as mock_rmtree, \
         patch("routes.packages.auth.audit_log") as mock_audit:
        res = auth_client.get("/api/devices/s1/packages/com.example.app/pull")
        assert res.status_code == 200
        res.close()  # must happen while shutil.rmtree is still patched
        mock_rmtree.assert_called_once_with(str(tmp_path), ignore_errors=True)
    mock_audit.assert_called_once_with("package_pull_apk", {"serial": "s1", "package": "com.example.app"})


def test_pull_apk_maps_adb_error_and_cleans_up(auth_client, tmp_path):
    with patch("routes.packages.tempfile.mkdtemp", return_value=str(tmp_path)), \
         patch("routes.packages.adb_packages.pull_apk", side_effect=adb_manager.AdbError("no apk")), \
         patch("routes.packages.shutil.rmtree") as mock_rmtree:
        res = auth_client.get("/api/devices/s1/packages/com.example.app/pull")
    assert res.status_code == 400
    mock_rmtree.assert_called_once_with(str(tmp_path), ignore_errors=True)
