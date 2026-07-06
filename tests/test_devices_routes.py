from unittest.mock import patch

from adb import manager as adb_manager


def test_get_devices_success(auth_client):
    with patch("routes.devices.adb_devices.list_devices", return_value=[{"serial": "s1"}]), \
         patch("routes.devices.adb_devices.list_fastboot_devices", return_value=[]):
        res = auth_client.get("/api/devices")
    assert res.status_code == 200
    assert res.get_json()["devices"] == [{"serial": "s1"}]


def test_get_devices_maps_adb_not_installed(auth_client):
    with patch("routes.devices.adb_devices.list_devices", side_effect=adb_manager.AdbNotInstalledError("no adb")):
        res = auth_client.get("/api/devices")
    assert res.status_code == 503
    assert res.get_json()["error"] == "adb_not_installed"


def test_get_device_detail_success(auth_client):
    with patch("routes.devices.adb_devices.get_device_detail", return_value={"serial": "s1"}):
        res = auth_client.get("/api/devices/s1")
    assert res.status_code == 200
    assert res.get_json()["device"] == {"serial": "s1"}


def test_get_device_detail_maps_adb_error(auth_client):
    with patch("routes.devices.adb_devices.get_device_detail", side_effect=adb_manager.AdbError("bad serial")):
        res = auth_client.get("/api/devices/s1")
    assert res.status_code == 400
    assert res.get_json()["error"] == "bad serial"


def test_get_device_detail_maps_adb_not_installed(auth_client):
    with patch("routes.devices.adb_devices.get_device_detail", side_effect=adb_manager.AdbNotInstalledError("no adb")):
        res = auth_client.get("/api/devices/s1")
    assert res.status_code == 503


def test_get_device_overview_success(auth_client):
    with patch("routes.devices.adb_dashboard.get_overview", return_value={"cpu_mem": {}}):
        res = auth_client.get("/api/devices/s1/overview")
    assert res.status_code == 200
    assert res.get_json()["overview"] == {"cpu_mem": {}}


def test_get_device_overview_maps_adb_error(auth_client):
    with patch("routes.devices.adb_dashboard.get_overview", side_effect=adb_manager.AdbError("boom")):
        res = auth_client.get("/api/devices/s1/overview")
    assert res.status_code == 400


def test_devices_routes_require_login(client):
    assert client.get("/api/devices").status_code == 401
    assert client.get("/api/devices/s1").status_code == 401
    assert client.get("/api/devices/s1/overview").status_code == 401
