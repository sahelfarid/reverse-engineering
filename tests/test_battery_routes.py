from unittest.mock import patch

from adb import manager as adb_manager


def test_hardware_success(auth_client):
    with patch("routes.battery.adb_battery.get_hardware_detail", return_value={"cpu": {"cores": 8}}):
        res = auth_client.get("/api/devices/s1/hardware")
    assert res.status_code == 200
    assert res.get_json()["hardware"] == {"cpu": {"cores": 8}}


def test_hardware_maps_adb_not_installed(auth_client):
    with patch("routes.battery.adb_battery.get_hardware_detail", side_effect=adb_manager.AdbNotInstalledError("x")):
        res = auth_client.get("/api/devices/s1/hardware")
    assert res.status_code == 503


def test_hardware_maps_adb_error(auth_client):
    with patch("routes.battery.adb_battery.get_hardware_detail", side_effect=adb_manager.AdbError("bad")):
        res = auth_client.get("/api/devices/s1/hardware")
    assert res.status_code == 400


def test_hardware_requires_login(client):
    assert client.get("/api/devices/s1/hardware").status_code == 401
