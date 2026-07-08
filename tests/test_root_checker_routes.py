import json
from unittest.mock import patch

from adb import manager as adb_manager


def test_rootcheck_get_is_static_only(auth_client):
    with patch("routes.root_checker.root_checker.get_report", return_value={"verdict": "no root detection evidence found"}) as mock_report:
        res = auth_client.get("/api/devices/s1/packages/com.example.app/rootcheck")
    assert res.status_code == 200
    assert res.get_json()["report"] == {"verdict": "no root detection evidence found"}
    mock_report.assert_called_once_with("s1", "com.example.app", run_dynamic=False)


def test_rootcheck_get_requires_login(client):
    assert client.get("/api/devices/s1/packages/com.example.app/rootcheck").status_code == 401


def test_rootcheck_get_maps_adb_not_installed(auth_client):
    with patch("routes.root_checker.root_checker.get_report", side_effect=adb_manager.AdbNotInstalledError("x")):
        res = auth_client.get("/api/devices/s1/packages/com.example.app/rootcheck")
    assert res.status_code == 503


def test_rootcheck_get_maps_adb_error(auth_client):
    with patch("routes.root_checker.root_checker.get_report", side_effect=adb_manager.AdbError("bad")):
        res = auth_client.get("/api/devices/s1/packages/com.example.app/rootcheck")
    assert res.status_code == 400


def test_rootcheck_post_runs_dynamic_and_audits(auth_client):
    with patch("routes.root_checker.root_checker.get_report", return_value={"verdict": "root detection implemented (static + dynamic evidence)"}) as mock_report:
        res = auth_client.post(
            "/api/devices/s1/packages/com.example.app/rootcheck",
            data=json.dumps({"duration_sec": 6}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    mock_report.assert_called_once_with("s1", "com.example.app", run_dynamic=True, dynamic_duration_sec=6.0)


def test_rootcheck_post_clamps_duration_to_bounds(auth_client):
    with patch("routes.root_checker.root_checker.get_report", return_value={"verdict": "x"}) as mock_report:
        auth_client.post(
            "/api/devices/s1/packages/com.example.app/rootcheck",
            data=json.dumps({"duration_sec": 999}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert mock_report.call_args.kwargs["dynamic_duration_sec"] == 15.0


def test_rootcheck_post_uses_default_duration_when_missing(auth_client):
    with patch("routes.root_checker.root_checker.get_report", return_value={"verdict": "x"}) as mock_report:
        auth_client.post(
            "/api/devices/s1/packages/com.example.app/rootcheck",
            data=json.dumps({}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert mock_report.call_args.kwargs["dynamic_duration_sec"] == 4.0


def test_rootcheck_post_requires_csrf(auth_client):
    res = auth_client.post(
        "/api/devices/s1/packages/com.example.app/rootcheck",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert res.status_code == 403


def test_rootcheck_post_requires_login(client):
    res = client.post("/api/devices/s1/packages/com.example.app/rootcheck", data=json.dumps({}), content_type="application/json")
    assert res.status_code == 401
