import json

import pytest
from werkzeug.security import generate_password_hash

import config
from app import app as flask_app

TEST_PASSWORD = "test-password-123"


@pytest.fixture
def client():
    """Flask test client with a known password set, no session yet."""
    flask_app.config.update(TESTING=True)
    settings = config.load_settings()
    settings["password_hash"] = generate_password_hash(TEST_PASSWORD)
    config.save_settings(settings)
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def auth_client(client):
    """Same client, already logged in, with the CSRF token stashed on it."""
    res = client.post(
        "/api/auth/login",
        data=json.dumps({"password": TEST_PASSWORD}),
        content_type="application/json",
    )
    client.csrf_token = res.get_json()["csrf_token"]
    return client
