import json

import pytest
from werkzeug.security import generate_password_hash

import config
from adb import manager as adb_manager
from app import app as flask_app

TEST_PASSWORD = "test-password-123"


def _first_online_device_serial():
    """Return the serial of the first authorized, online device, or None.

    Used to gate real-device smoke tests: those tests need actual `dumpsys`/
    `/proc` output from a device, which a mocked unit test can't produce, so
    they skip cleanly wherever no device/emulator is attached (e.g. CI).
    """
    try:
        proc = adb_manager.run(["devices"], timeout=10)
    except adb_manager.AdbError:
        return None
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            return parts[0]
    return None


@pytest.fixture(scope="session")
def real_device_serial():
    """Serial of a real, authorized, online ADB device -- skips the test if none is attached."""
    serial = _first_online_device_serial()
    if not serial:
        pytest.skip("no authorized ADB device/emulator attached; skipping real-device smoke test")
    return serial


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
