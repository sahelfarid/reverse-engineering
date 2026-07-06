import json
from unittest.mock import patch

from adb import manager as adb_manager


def _post(auth_client, url, payload=None):
    return auth_client.post(
        url, data=json.dumps(payload if payload is not None else {}), content_type="application/json",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )


def test_network_info_success(auth_client):
    with patch("routes.network.adb_network.get_network_info", return_value={"wifi_ip": "1.2.3.4"}):
        res = auth_client.get("/api/devices/s1/network")
    assert res.status_code == 200


def test_ping_success(auth_client):
    with patch("routes.network.adb_network.ping_from_device", return_value={"ok": True, "output": ""}):
        res = _post(auth_client, "/api/devices/s1/network/ping", {"host": "8.8.8.8"})
    assert res.status_code == 200


def test_forwards_list_success(auth_client):
    with patch("routes.network.adb_network.list_forwards", return_value=[]):
        res = auth_client.get("/api/forwards")
    assert res.status_code == 200


def test_forward_add_success_and_audit_log(auth_client):
    with patch("routes.network.adb_network.add_forward", return_value={"ok": True, "error": None}), \
         patch("routes.network.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/forward", {"local": "tcp:5555", "remote": "tcp:5555"})
    assert res.status_code == 200
    mock_audit.assert_called_once_with("forward_add", {"serial": "s1", "local": "tcp:5555", "remote": "tcp:5555"})


def test_forward_add_maps_adb_error(auth_client):
    with patch("routes.network.adb_network.add_forward", side_effect=adb_manager.AdbError("invalid port spec")):
        res = _post(auth_client, "/api/devices/s1/forward", {"local": "tcp:99999", "remote": "tcp:5555"})
    assert res.status_code == 400


def test_forward_remove_success_and_audit_log(auth_client):
    with patch("routes.network.adb_network.remove_forward", return_value={"ok": True}), \
         patch("routes.network.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/forward/remove", {"local": "tcp:5555"})
    assert res.status_code == 200
    mock_audit.assert_called_once_with("forward_remove", {"local": "tcp:5555"})


def test_reverse_list_success(auth_client):
    with patch("routes.network.adb_network.list_reverses", return_value=[]):
        res = auth_client.get("/api/devices/s1/reverse")
    assert res.status_code == 200


def test_reverse_add_success_and_audit_log(auth_client):
    with patch("routes.network.adb_network.add_reverse", return_value={"ok": True, "error": None}), \
         patch("routes.network.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/reverse", {"remote": "tcp:9000", "local": "tcp:9000"})
    assert res.status_code == 200
    mock_audit.assert_called_once_with("reverse_add", {"serial": "s1", "remote": "tcp:9000", "local": "tcp:9000"})


def test_reverse_remove_success_and_audit_log(auth_client):
    with patch("routes.network.adb_network.remove_reverse", return_value={"ok": True}), \
         patch("routes.network.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/reverse/remove", {"remote": "tcp:9000"})
    assert res.status_code == 200
    mock_audit.assert_called_once_with("reverse_remove", {"serial": "s1", "remote": "tcp:9000"})


def test_enable_tcpip_success_and_audit_log(auth_client):
    with patch("routes.network.adb_wireless.enable_tcpip", return_value={"ok": True, "output": ""}), \
         patch("routes.network.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/devices/s1/wireless/enable-tcpip", {"port": 5555})
    assert res.status_code == 200
    mock_audit.assert_called_once_with("wireless_enable_tcpip", {"serial": "s1", "port": 5555})


def test_wireless_address_success(auth_client):
    with patch("routes.network.adb_wireless.get_device_wifi_address", return_value="1.2.3.4:5555"):
        res = auth_client.get("/api/devices/s1/wireless/address?port=5555")
    assert res.status_code == 200
    assert res.get_json()["address"] == "1.2.3.4:5555"


def test_wireless_address_rejects_malformed_port(auth_client):
    res = auth_client.get("/api/devices/s1/wireless/address?port=not-a-port")
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_port"


def test_wireless_connect_success_and_audit_log(auth_client):
    with patch("routes.network.adb_wireless.connect", return_value={"ok": True, "output": ""}), \
         patch("routes.network.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/wireless/connect", {"address": "1.2.3.4:5555"})
    assert res.status_code == 200
    mock_audit.assert_called_once_with("wireless_connect", {"address": "1.2.3.4:5555"})


def test_wireless_disconnect_success_and_audit_log(auth_client):
    with patch("routes.network.adb_wireless.disconnect", return_value={"ok": True, "output": ""}), \
         patch("routes.network.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/wireless/disconnect", {"address": "1.2.3.4:5555"})
    assert res.status_code == 200
    mock_audit.assert_called_once_with("wireless_disconnect", {"address": "1.2.3.4:5555"})


def test_known_devices_list(auth_client):
    with patch("routes.network.adb_wireless.list_known_devices", return_value={"phone": "1.2.3.4:5555"}):
        res = auth_client.get("/api/wireless/known")
    assert res.status_code == 200


def test_known_device_save_success_and_audit_log(auth_client):
    with patch("routes.network.adb_wireless.save_known_device", return_value={"ok": True}), \
         patch("routes.network.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/wireless/known", {"name": "phone", "address": "1.2.3.4:5555"})
    assert res.status_code == 200
    mock_audit.assert_called_once_with("wireless_known_save", {"name": "phone", "address": "1.2.3.4:5555"})


def test_known_device_save_failure_skips_audit_log(auth_client):
    with patch("routes.network.adb_wireless.save_known_device", return_value={"ok": False, "error": "invalid_address"}), \
         patch("routes.network.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/wireless/known", {"name": "phone", "address": "bad"})
    assert res.status_code == 200
    assert res.get_json()["ok"] is False
    mock_audit.assert_not_called()


def test_known_device_delete_success_and_audit_log(auth_client):
    with patch("routes.network.adb_wireless.delete_known_device", return_value={"ok": True}), \
         patch("routes.network.auth.audit_log") as mock_audit:
        res = auth_client.delete("/api/wireless/known/phone", headers={"X-CSRF-Token": auth_client.csrf_token})
    assert res.status_code == 200
    mock_audit.assert_called_once_with("wireless_known_delete", {"name": "phone"})


def test_reconnect_all_success_and_audit_log(auth_client):
    with patch("routes.network.adb_wireless.reconnect_known_devices", return_value=[{"name": "phone", "ok": True}]), \
         patch("routes.network.auth.audit_log") as mock_audit:
        res = _post(auth_client, "/api/wireless/reconnect-all")
    assert res.status_code == 200
    mock_audit.assert_called_once_with("wireless_reconnect_all", {"count": 1})


def test_mutating_routes_require_csrf(client):
    client.post("/api/auth/login", data=json.dumps({"password": "test-password-123"}), content_type="application/json")
    assert client.post("/api/devices/s1/forward").status_code == 403
    assert client.post("/api/wireless/connect").status_code == 403
