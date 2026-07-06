from unittest.mock import MagicMock, patch

from adb import wireless


def test_enable_tcpip_success_and_failure():
    with patch("adb.wireless.manager.run", return_value=MagicMock(returncode=0, stdout="restarting in TCP mode", stderr="")) as mock_run:
        result = wireless.enable_tcpip("s1", port=5555)
    assert result["ok"] is True
    assert mock_run.call_args[0][0] == ["-s", "s1", "tcpip", "5555"]
    with patch("adb.wireless.manager.run", return_value=MagicMock(returncode=1, stdout="", stderr="error")):
        result = wireless.enable_tcpip("s1")
    assert result["ok"] is False


def test_get_device_wifi_address_success_and_no_ip():
    with patch("adb.wireless.network.get_network_info", return_value={"wifi_ip": "192.168.1.50"}):
        assert wireless.get_device_wifi_address("s1", port=5555) == "192.168.1.50:5555"
    with patch("adb.wireless.network.get_network_info", return_value={"wifi_ip": None}):
        assert wireless.get_device_wifi_address("s1") is None


def test_connect_rejects_invalid_address():
    assert wireless.connect("; rm -rf /") == {"ok": False, "error": "invalid_address"}


def test_connect_rejects_out_of_range_port():
    assert wireless.connect("192.168.1.50:99999") == {"ok": False, "error": "invalid_address"}


def test_connect_success_and_failure_output():
    with patch("adb.wireless.manager.run", return_value=MagicMock(stdout="connected to 192.168.1.50:5555")):
        result = wireless.connect("192.168.1.50:5555")
    assert result["ok"] is True

    with patch("adb.wireless.manager.run", return_value=MagicMock(stdout="failed to connect to 192.168.1.50:5555")):
        result = wireless.connect("192.168.1.50:5555")
    assert result["ok"] is False

    with patch("adb.wireless.manager.run", return_value=MagicMock(stdout="cannot connect to 192.168.1.50:5555")):
        result = wireless.connect("192.168.1.50:5555")
    assert result["ok"] is False


def test_disconnect_rejects_invalid_and_succeeds():
    assert wireless.disconnect("bad-address") == {"ok": False, "error": "invalid_address"}
    with patch("adb.wireless.manager.run", return_value=MagicMock(returncode=0, stdout="disconnected")):
        result = wireless.disconnect("192.168.1.50:5555")
    assert result["ok"] is True


def test_save_known_device_rejects_invalid_name():
    for bad_name in ["", "   ", None, 123, "x" * (wireless.MAX_KNOWN_DEVICE_NAME_LEN + 1)]:
        result = wireless.save_known_device(bad_name, "192.168.1.50:5555")
        assert result == {"ok": False, "error": "invalid_name"}


def test_save_known_device_rejects_invalid_address(monkeypatch):
    monkeypatch.setattr(wireless.config, "load_known_devices", lambda: {})
    result = wireless.save_known_device("phone", "not-an-address")
    assert result == {"ok": False, "error": "invalid_address"}


def test_save_known_device_success(monkeypatch):
    store = {}
    monkeypatch.setattr(wireless.config, "load_known_devices", lambda: store)
    monkeypatch.setattr(wireless.config, "save_known_devices", lambda d: store.update(d))
    result = wireless.save_known_device("phone", "192.168.1.50:5555")
    assert result == {"ok": True}
    assert store["phone"] == "192.168.1.50:5555"


def test_delete_known_device_removes_existing_and_is_idempotent(monkeypatch):
    store = {"phone": "192.168.1.50:5555"}
    monkeypatch.setattr(wireless.config, "load_known_devices", lambda: store)
    monkeypatch.setattr(wireless.config, "save_known_devices", lambda d: store.update(d))
    assert wireless.delete_known_device("phone") == {"ok": True}
    assert "phone" not in store
    assert wireless.delete_known_device("does-not-exist") == {"ok": True}


def test_reconnect_known_devices_connects_each_one(monkeypatch):
    monkeypatch.setattr(wireless.config, "load_known_devices", lambda: {"phone": "192.168.1.50:5555", "tablet": "192.168.1.51:5555"})
    with patch("adb.wireless.connect", return_value={"ok": True, "output": ""}) as mock_connect:
        results = wireless.reconnect_known_devices()
    assert len(results) == 2
    assert {r["name"] for r in results} == {"phone", "tablet"}
    assert mock_connect.call_count == 2
