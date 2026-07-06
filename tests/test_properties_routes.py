from unittest.mock import patch

from adb import manager as adb_manager


def test_get_properties_success(auth_client):
    with patch("routes.properties.adb_properties.get_properties", return_value={"categories": {}, "total": 0}):
        res = auth_client.get("/api/devices/s1/properties")
    assert res.status_code == 200
    assert res.get_json()["total"] == 0


def test_get_properties_maps_adb_not_installed(auth_client):
    with patch("routes.properties.adb_properties.get_properties", side_effect=adb_manager.AdbNotInstalledError("x")):
        res = auth_client.get("/api/devices/s1/properties")
    assert res.status_code == 503
    assert res.get_json()["error"] == "adb_not_installed"


def test_get_properties_maps_adb_error(auth_client):
    with patch("routes.properties.adb_properties.get_properties", side_effect=adb_manager.AdbError("getprop failed")):
        res = auth_client.get("/api/devices/s1/properties")
    assert res.status_code == 400
    assert res.get_json()["error"] == "getprop failed"


def test_get_properties_requires_login(client):
    assert client.get("/api/devices/s1/properties").status_code == 401
