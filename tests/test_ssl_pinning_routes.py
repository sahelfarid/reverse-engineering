import json
from unittest.mock import patch

from adb import manager as adb_manager


# --- POST /sslpinning/detect --------------------------------------------------

def test_detect_success_and_audits(auth_client):
    with patch("routes.ssl_pinning.ssl_pinning.get_detection_report", return_value={"verdict": "no SSL/TLS pinning evidence found"}) as mock_report, \
         patch("routes.ssl_pinning.auth.audit_log") as mock_audit:
        res = auth_client.post(
            "/api/devices/s1/packages/com.example.app/sslpinning/detect",
            data=json.dumps({"duration_sec": 6}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    mock_report.assert_called_once_with("s1", "com.example.app", run_dynamic=True, dynamic_duration_sec=6.0)
    mock_audit.assert_called_once()


def test_detect_clamps_duration(auth_client):
    with patch("routes.ssl_pinning.ssl_pinning.get_detection_report", return_value={"verdict": "x"}) as mock_report:
        auth_client.post(
            "/api/devices/s1/packages/com.example.app/sslpinning/detect",
            data=json.dumps({"duration_sec": 999}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert mock_report.call_args.kwargs["dynamic_duration_sec"] == 15.0


def test_detect_can_disable_dynamic(auth_client):
    with patch("routes.ssl_pinning.ssl_pinning.get_detection_report", return_value={"verdict": "x"}) as mock_report:
        auth_client.post(
            "/api/devices/s1/packages/com.example.app/sslpinning/detect",
            data=json.dumps({"dynamic": False}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert mock_report.call_args.kwargs["run_dynamic"] is False


def test_detect_maps_adb_error(auth_client):
    with patch("routes.ssl_pinning.ssl_pinning.get_detection_report", side_effect=adb_manager.AdbError("bad")):
        res = auth_client.post(
            "/api/devices/s1/packages/com.example.app/sslpinning/detect",
            data=json.dumps({}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 400


def test_detect_maps_adb_not_installed(auth_client):
    with patch("routes.ssl_pinning.ssl_pinning.get_detection_report", side_effect=adb_manager.AdbNotInstalledError("x")):
        res = auth_client.post(
            "/api/devices/s1/packages/com.example.app/sslpinning/detect",
            data=json.dumps({}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 503


def test_detect_requires_csrf(auth_client):
    res = auth_client.post(
        "/api/devices/s1/packages/com.example.app/sslpinning/detect",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert res.status_code == 403


def test_detect_requires_login(client):
    res = client.post("/api/devices/s1/packages/com.example.app/sslpinning/detect", data=json.dumps({}), content_type="application/json")
    assert res.status_code == 401


# --- POST /frida/sslpinning/bypass --------------------------------------------

def test_bypass_requires_confirm_flag(auth_client):
    res = auth_client.post(
        "/api/devices/s1/frida/sslpinning/bypass",
        data=json.dumps({"spawn": "com.example.app", "script_name": "universal-trust-manager-bypass"}),
        content_type="application/json",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "confirmation_required"


def test_bypass_requires_target(auth_client):
    res = auth_client.post(
        "/api/devices/s1/frida/sslpinning/bypass",
        data=json.dumps({"confirm": True, "script_name": "universal-trust-manager-bypass"}),
        content_type="application/json",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_target"


def test_bypass_success_spawns_and_audits(auth_client):
    with patch("routes.ssl_pinning.ssl_pinning.attach_bypass", return_value={"ok": True, "session_id": "sess1", "script_sha256": "abc"}) as mock_attach, \
         patch("routes.ssl_pinning.auth.audit_log") as mock_audit:
        res = auth_client.post(
            "/api/devices/s1/frida/sslpinning/bypass",
            data=json.dumps({"confirm": True, "spawn": "com.example.app", "script_name": "universal-trust-manager-bypass"}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    mock_attach.assert_called_once_with("s1", {"spawn": "com.example.app"}, "universal-trust-manager-bypass", None)
    mock_audit.assert_called_once()
    assert mock_audit.call_args.args[0] == "ssl_pinning_bypass"
    assert mock_audit.call_args.args[1]["authorized"] is True


def test_bypass_with_existing_pid_target(auth_client):
    with patch("routes.ssl_pinning.ssl_pinning.attach_bypass", return_value={"ok": True, "session_id": "sess1", "script_sha256": "abc"}) as mock_attach:
        auth_client.post(
            "/api/devices/s1/frida/sslpinning/bypass",
            data=json.dumps({"confirm": True, "target": {"pid": 123}, "script_source": "custom js"}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    mock_attach.assert_called_once_with("s1", {"pid": 123}, None, "custom js")


def test_bypass_maps_adb_error(auth_client):
    with patch("routes.ssl_pinning.ssl_pinning.attach_bypass", side_effect=adb_manager.AdbError("script not found")):
        res = auth_client.post(
            "/api/devices/s1/frida/sslpinning/bypass",
            data=json.dumps({"confirm": True, "spawn": "com.example.app", "script_name": "nope"}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 400


def test_bypass_requires_csrf(auth_client):
    res = auth_client.post(
        "/api/devices/s1/frida/sslpinning/bypass",
        data=json.dumps({"confirm": True, "spawn": "com.example.app"}),
        content_type="application/json",
    )
    assert res.status_code == 403


def test_bypass_requires_login(client):
    res = client.post("/api/devices/s1/frida/sslpinning/bypass", data=json.dumps({}), content_type="application/json")
    assert res.status_code == 401


# --- script store routes -------------------------------------------------------

def test_list_scripts_success(auth_client):
    with patch("routes.ssl_pinning.ssl_pinning.list_scripts", return_value={"universal-trust-manager-bypass": {}}):
        res = auth_client.get("/api/frida/sslpinning/scripts")
    assert res.status_code == 200
    assert "universal-trust-manager-bypass" in res.get_json()["scripts"]


def test_list_scripts_requires_login(client):
    assert client.get("/api/frida/sslpinning/scripts").status_code == 401


def test_save_script_success_and_audits(auth_client):
    with patch("routes.ssl_pinning.ssl_pinning.save_script", return_value={"ok": True, "name": "my-bypass"}), \
         patch("routes.ssl_pinning.auth.audit_log") as mock_audit:
        res = auth_client.post(
            "/api/frida/sslpinning/scripts",
            data=json.dumps({"name": "my-bypass", "source": "console.log('x');"}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    mock_audit.assert_called_once()
    assert mock_audit.call_args.args[0] == "ssl_pinning_script_save"


def test_save_script_maps_adb_error(auth_client):
    with patch("routes.ssl_pinning.ssl_pinning.save_script", side_effect=adb_manager.AdbError("read-only")):
        res = auth_client.post(
            "/api/frida/sslpinning/scripts",
            data=json.dumps({"name": "universal-trust-manager-bypass", "source": "x"}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 400


def test_save_script_requires_csrf(auth_client):
    res = auth_client.post(
        "/api/frida/sslpinning/scripts",
        data=json.dumps({"name": "x", "source": "y"}),
        content_type="application/json",
    )
    assert res.status_code == 403


def test_delete_script_success_and_audits(auth_client):
    with patch("routes.ssl_pinning.ssl_pinning.delete_script", return_value={"ok": True}), \
         patch("routes.ssl_pinning.auth.audit_log") as mock_audit:
        res = auth_client.delete(
            "/api/frida/sslpinning/scripts/my-bypass",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    mock_audit.assert_called_once_with("ssl_pinning_script_delete", {"name": "my-bypass"})


def test_delete_script_requires_csrf(auth_client):
    res = auth_client.delete("/api/frida/sslpinning/scripts/my-bypass")
    assert res.status_code == 403


def test_delete_script_requires_login(client):
    assert client.delete("/api/frida/sslpinning/scripts/my-bypass").status_code == 401
