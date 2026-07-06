import json
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

import config
from adb import manager as adb_manager
from app import app as flask_app

TEST_PASSWORD = "test-password-123"


@pytest.fixture
def client():
    flask_app.config.update(TESTING=True)
    settings = config.load_settings()
    settings["password_hash"] = generate_password_hash(TEST_PASSWORD)
    config.save_settings(settings)
    with flask_app.test_client() as c:
        yield c


def test_index_serves_login_page_when_unauthenticated(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Sign in" in res.data or b"password" in res.data.lower()


def test_protected_api_requires_auth(client):
    res = client.get("/api/devices")
    assert res.status_code == 401
    assert res.get_json()["error"] == "unauthenticated"


def test_login_rejects_wrong_password(client):
    res = client.post("/api/auth/login", data=json.dumps({"password": "wrong"}), content_type="application/json")
    assert res.status_code == 401


def test_login_accepts_correct_password_and_gates_devices_on_adb(client):
    res = client.post("/api/auth/login", data=json.dumps({"password": TEST_PASSWORD}), content_type="application/json")
    assert res.status_code == 200
    assert res.get_json()["ok"] is True

    devices_res = client.get("/api/devices")
    # Whether adb happens to be installed on the test machine or not, the
    # route must not 401 anymore now that we're authenticated.
    assert devices_res.status_code in (200, 503)


def test_logout_clears_session_and_locks_out_subsequent_requests(client):
    client.post("/api/auth/login", data=json.dumps({"password": TEST_PASSWORD}), content_type="application/json")
    assert client.get("/api/devices").status_code in (200, 503)

    res = client.post("/api/auth/logout")
    assert res.status_code == 200
    assert res.get_json()["ok"] is True

    assert client.get("/api/devices").status_code == 401


def test_mutating_request_without_csrf_token_is_rejected(client):
    client.post("/api/auth/login", data=json.dumps({"password": TEST_PASSWORD}), content_type="application/json")
    res = client.post("/api/adb/install")
    assert res.status_code == 403
    assert res.get_json()["error"] == "csrf_failed"


def _login_and_get_csrf(client):
    res = client.post("/api/auth/login", data=json.dumps({"password": TEST_PASSWORD}), content_type="application/json")
    return res.get_json()["csrf_token"]


def test_update_settings_accepts_valid_known_keys(client):
    csrf = _login_and_get_csrf(client)
    res = client.post(
        "/api/settings",
        data=json.dumps({"theme": "light", "shell_timeout_sec": 45}),
        content_type="application/json",
        headers={"X-CSRF-Token": csrf},
    )
    body = res.get_json()
    assert res.status_code == 200
    assert body["ok"] is True
    assert body["settings"]["theme"] == "light"
    assert body["settings"]["shell_timeout_sec"] == 45
    assert "rejected" not in body


def test_update_settings_rejects_unknown_and_out_of_range_keys(client):
    csrf = _login_and_get_csrf(client)
    res = client.post(
        "/api/settings",
        data=json.dumps({"theme": "not-a-theme", "shell_timeout_sec": 99999, "made_up_key": 1}),
        content_type="application/json",
        headers={"X-CSRF-Token": csrf},
    )
    body = res.get_json()
    assert res.status_code == 200
    assert set(body["rejected"]) == {"theme", "shell_timeout_sec", "made_up_key"}


def test_update_settings_ignores_password_hash_field(client):
    csrf = _login_and_get_csrf(client)
    res = client.post(
        "/api/settings",
        data=json.dumps({"password_hash": "attacker-controlled"}),
        content_type="application/json",
        headers={"X-CSRF-Token": csrf},
    )
    body = res.get_json()
    assert res.status_code == 200
    assert "password_hash" in body["rejected"]
    assert "password_hash" not in body["settings"]


def test_change_password_rejects_wrong_current_password(client):
    csrf = _login_and_get_csrf(client)
    res = client.post(
        "/api/auth/change-password",
        data=json.dumps({"current_password": "wrong", "new_password": "new-password-123"}),
        content_type="application/json",
        headers={"X-CSRF-Token": csrf},
    )
    assert res.status_code == 401
    assert res.get_json()["error"] == "invalid_current_password"


def test_change_password_rejects_short_new_password(client):
    csrf = _login_and_get_csrf(client)
    res = client.post(
        "/api/auth/change-password",
        data=json.dumps({"current_password": TEST_PASSWORD, "new_password": "abc"}),
        content_type="application/json",
        headers={"X-CSRF-Token": csrf},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "new_password_too_short"


def test_change_password_success_updates_hash_and_audit_logs(client):
    csrf = _login_and_get_csrf(client)
    with patch("routes.core.auth.audit_log") as mock_audit:
        res = client.post(
            "/api/auth/change-password",
            data=json.dumps({"current_password": TEST_PASSWORD, "new_password": "new-password-123"}),
            content_type="application/json",
            headers={"X-CSRF-Token": csrf},
        )
    assert res.status_code == 200
    assert res.get_json()["ok"] is True
    mock_audit.assert_called_once_with("password_changed", {})

    # Old password not accepted; new password is, in a follow-up login.
    stale_login = client.post(
        "/api/auth/login", data=json.dumps({"password": TEST_PASSWORD}), content_type="application/json",
    )
    assert stale_login.status_code == 401
    fresh_login = client.post(
        "/api/auth/login", data=json.dumps({"password": "new-password-123"}), content_type="application/json",
    )
    assert fresh_login.status_code == 200


def test_change_password_requires_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": TEST_PASSWORD}), content_type="application/json")
    res = client.post(
        "/api/auth/change-password",
        data=json.dumps({"current_password": TEST_PASSWORD, "new_password": "new-password-123"}),
        content_type="application/json",
    )
    assert res.status_code == 403


def test_adb_install_success(client):
    csrf = _login_and_get_csrf(client)
    fake_status = {"installed": True, "source": "vendor", "version": "34.0.0", "path": "/vendor/adb"}
    with patch("routes.core.adb_manager.install_adb", return_value=fake_status), \
         patch("routes.core.auth.audit_log") as mock_audit:
        res = client.post(
            "/api/adb/install", content_type="application/json", headers={"X-CSRF-Token": csrf},
        )
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["status"] == fake_status
    mock_audit.assert_called_once_with("adb_install", {"path": "/vendor/adb"})


def test_adb_install_maps_install_error(client):
    csrf = _login_and_get_csrf(client)
    with patch("routes.core.adb_manager.install_adb", side_effect=adb_manager.AdbInstallError("download failed")):
        res = client.post(
            "/api/adb/install", content_type="application/json", headers={"X-CSRF-Token": csrf},
        )
    assert res.status_code == 500
    assert res.get_json()["ok"] is False
