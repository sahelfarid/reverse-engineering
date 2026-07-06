import json

import pytest
from werkzeug.security import generate_password_hash

import config
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
