"""Real-device smoke test for adb/app_inspector.py.

Mocked unit tests (tests/test_app_inspector.py) cover the parsing logic
against fixed `dumpsys` fixtures, but can't catch OEM-specific output-format
drift. This test runs the real parser against a real, attached device's
`dumpsys package android` output -- the "android" system package is present
on every real Android device/emulator, so this needs no test fixture install.
It skips automatically (via the `real_device_serial` fixture) when no
authorized device is attached, e.g. in CI.
"""
from adb import app_inspector


def test_get_permissions_real_device_smoke(real_device_serial):
    result = app_inspector.get_permissions(real_device_serial, "android")
    assert isinstance(result["requested"], list)
    assert isinstance(result["granted"], list)
    assert isinstance(result["denied"], list)
    # The system package always requests and is granted at least one permission.
    assert result["requested"] or result["granted"]


def test_get_components_real_device_smoke(real_device_serial):
    result = app_inspector.get_components(real_device_serial, "android")
    assert set(result.keys()) == {"activities", "receivers", "services", "providers"}
    for value in result.values():
        assert isinstance(value, list)


def test_get_app_detail_real_device_smoke(real_device_serial):
    result = app_inspector.get_app_detail(real_device_serial, "android")
    assert result["package"] == "android"
    assert "permissions" in result and "components" in result and "data" in result
