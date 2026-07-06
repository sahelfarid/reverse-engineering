from unittest.mock import patch

from adb import manager as adb_manager


def test_integrity_success(auth_client):
    with patch("routes.root_detection.root_detection.get_integrity_report", return_value={"verdict": "not detected"}):
        res = auth_client.get("/api/devices/s1/integrity")
    assert res.status_code == 200
    assert res.get_json()["report"] == {"verdict": "not detected"}


def test_integrity_maps_adb_not_installed(auth_client):
    with patch("routes.root_detection.root_detection.get_integrity_report", side_effect=adb_manager.AdbNotInstalledError("x")):
        res = auth_client.get("/api/devices/s1/integrity")
    assert res.status_code == 503


def test_integrity_maps_adb_error(auth_client):
    with patch("routes.root_detection.root_detection.get_integrity_report", side_effect=adb_manager.AdbError("bad")):
        res = auth_client.get("/api/devices/s1/integrity")
    assert res.status_code == 400


def test_integrity_requires_login(client):
    assert client.get("/api/devices/s1/integrity").status_code == 401
