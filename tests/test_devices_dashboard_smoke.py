"""Real-device smoke test for adb/devices.py and adb/dashboard.py.

Mocked unit tests (tests/test_devices.py, tests/test_dashboard.py) cover the
parsers against fixed `dumpsys`/`/proc` fixtures, but can't catch OEM-specific
output-format drift. This test runs the real composers against a real,
attached device. It skips automatically (via the `real_device_serial` fixture)
when no authorized device is attached, e.g. in CI.
"""
from adb import dashboard, devices


def test_list_devices_real_device_smoke(real_device_serial):
    found = devices.list_devices()
    assert any(d["serial"] == real_device_serial and d["state"] == "device" for d in found)


def test_get_device_detail_real_device_smoke(real_device_serial):
    detail = devices.get_device_detail(real_device_serial)
    assert detail["serial"] == real_device_serial
    assert "properties" in detail and "battery" in detail and "storage" in detail
    # At least one basic property should resolve on any real device.
    assert any(detail["properties"].values())


def test_dashboard_overview_real_device_smoke(real_device_serial):
    overview = dashboard.get_overview(real_device_serial)
    assert set(overview.keys()) == {"cpu_mem", "apps", "screen", "foreground", "wifi", "root_available"}
    assert isinstance(overview["root_available"], bool)
