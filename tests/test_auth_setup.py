"""First-launch setup screen, optional password, "remember me", and the
forgot-password reset flow (auth.py's complete_setup()/reset_password(),
routes.core's /api/auth/setup and /api/auth/reset)."""
import json
import re

import pytest

import config
from app import app as flask_app

TEST_PASSWORD = "test-password-123"


@pytest.fixture
def fresh_client():
    """Flask test client starting from a not-yet-configured auth state (no
    password, setup not completed) -- the real first-launch condition."""
    flask_app.config.update(TESTING=True)
    settings = config.load_settings()
    settings["password_hash"] = None
    settings["auth_setup_complete"] = False
    config.save_settings(settings)
    with flask_app.test_client() as c:
        yield c


def test_first_launch_serves_setup_page(fresh_client):
    res = fresh_client.get("/")
    assert res.status_code == 200
    assert b"setup-form" in res.data


def test_setup_rejects_short_password(fresh_client):
    res = fresh_client.post(
        "/api/auth/setup", data=json.dumps({"password": "abc"}), content_type="application/json",
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "password_too_short"
    assert not config.load_settings()["password_hash"]


def test_setup_with_password_completes_setup_and_logs_in(fresh_client):
    res = fresh_client.post(
        "/api/auth/setup",
        data=json.dumps({"password": "a-real-password", "remember": True}),
        content_type="application/json",
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["csrf_token"]

    settings = config.load_settings()
    assert settings["auth_setup_complete"] is True
    assert settings["password_hash"]

    # Setup logged us straight in -- the dashboard renders, not the login form.
    dash = fresh_client.get("/")
    assert dash.status_code == 200
    assert b"login-form" not in dash.data
    assert b"setup-form" not in dash.data


def test_setup_skip_marks_complete_with_no_password_and_stays_open(fresh_client):
    res = fresh_client.post(
        "/api/auth/setup", data=json.dumps({"password": None}), content_type="application/json",
    )
    assert res.status_code == 200

    settings = config.load_settings()
    assert settings["auth_setup_complete"] is True
    assert not settings["password_hash"]

    # A brand new client with no session at all still reaches past login --
    # skipping the password is an open-access choice, not a one-time bypass.
    with flask_app.test_client() as anon:
        res2 = anon.get("/api/devices")
        assert res2.status_code != 401

        # It never called login_session() (which normally issues a CSRF
        # token), so index() must hand one out itself via ensure_csrf_token()
        # -- otherwise every mutating route would be permanently unreachable
        # in open-access mode.
        dash = anon.get("/")
        match = re.search(rb'window\.CSRF_TOKEN = "([0-9a-f]+)"', dash.data)
        assert match and match.group(1)


def test_setup_rejected_once_already_configured(fresh_client):
    fresh_client.post("/api/auth/setup", data=json.dumps({"password": None}), content_type="application/json")
    res = fresh_client.post(
        "/api/auth/setup", data=json.dumps({"password": "whatever123"}), content_type="application/json",
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "already_configured"


def test_reset_requires_confirm_flag(fresh_client):
    res = fresh_client.post("/api/auth/reset", data=json.dumps({}), content_type="application/json")
    assert res.status_code == 400
    assert res.get_json()["error"] == "confirmation_required"
    # A truthy-but-not-exactly-True value doesn't count either.
    res2 = fresh_client.post(
        "/api/auth/reset", data=json.dumps({"confirm": "yes"}), content_type="application/json",
    )
    assert res2.status_code == 400


def test_reset_clears_password_and_invalidates_existing_session(fresh_client):
    fresh_client.post(
        "/api/auth/setup", data=json.dumps({"password": "original-password"}), content_type="application/json",
    )
    assert config.load_settings()["password_hash"]
    assert fresh_client.get("/api/devices").status_code != 401  # logged in by setup

    res = fresh_client.post("/api/auth/reset", data=json.dumps({"confirm": True}), content_type="application/json")
    assert res.status_code == 200
    assert res.get_json()["ok"] is True

    settings = config.load_settings()
    assert not settings["password_hash"]
    assert settings["auth_setup_complete"] is False

    # Old session cookie is signed with the now-rotated secret key -- treated
    # as no session at all, so we're back at the setup screen.
    res2 = fresh_client.get("/")
    assert b"setup-form" in res2.data


def test_login_remember_sets_a_persistent_cookie(client):
    res = client.post(
        "/api/auth/login",
        data=json.dumps({"password": TEST_PASSWORD, "remember": True}),
        content_type="application/json",
    )
    assert res.status_code == 200
    set_cookie = res.headers.get("Set-Cookie", "")
    assert "Max-Age" in set_cookie or "Expires" in set_cookie


def test_login_without_remember_uses_a_session_only_cookie(client):
    res = client.post(
        "/api/auth/login", data=json.dumps({"password": TEST_PASSWORD}), content_type="application/json",
    )
    assert res.status_code == 200
    set_cookie = res.headers.get("Set-Cookie", "")
    assert "Max-Age" not in set_cookie and "Expires" not in set_cookie


def test_change_password_allows_initial_set_with_no_current_password(fresh_client):
    fresh_client.post("/api/auth/setup", data=json.dumps({"password": None}), content_type="application/json")
    # Open-access mode has no CSRF token from a login step -- index() must
    # still hand one out so mutating routes (like this one) are reachable.
    dash = fresh_client.get("/")
    match = re.search(rb'window\.CSRF_TOKEN = "([0-9a-f]+)"', dash.data)
    assert match, dash.data
    csrf_token = match.group(1).decode()

    res = fresh_client.post(
        "/api/auth/change-password",
        data=json.dumps({"current_password": "", "new_password": "brand-new-password"}),
        content_type="application/json",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert res.status_code == 200
    assert res.get_json()["ok"] is True
    assert config.load_settings()["password_hash"]
