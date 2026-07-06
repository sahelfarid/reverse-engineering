from unittest.mock import MagicMock, patch

import pytest

from adb import manager, network


def test_get_network_info_parses_all_fields():
    with patch("adb.network.manager.validate_serial", return_value="s1"), \
         patch("adb.network.manager.shell") as mock_shell:
        mock_shell.side_effect = [
            ("inet 192.168.1.50/24 brd 192.168.1.255 scope global wlan0\n", "", 0),
            ("default via 192.168.1.1 dev wlan0\n", "", 0),
            ("8.8.8.8\n", "", 0),
            ("8.8.4.4\n", "", 0),
            ("LTE\n", "", 0),
            ("mWifiState=enabled\n", "", 0),
        ]
        result = network.get_network_info("s1")
    assert result["wifi_ip"] == "192.168.1.50"
    assert result["wifi_prefix"] == "24"
    assert result["gateway"] == "192.168.1.1"
    assert result["dns1"] == "8.8.8.8"
    assert result["dns2"] == "8.8.4.4"
    assert result["mobile_network_type"] == "LTE"
    assert result["wifi_state_raw"] == "mWifiState=enabled"


def test_get_network_info_handles_missing_data():
    with patch("adb.network.manager.validate_serial", return_value="s1"), \
         patch("adb.network.manager.shell", return_value=("", "", 1)):
        result = network.get_network_info("s1")
    assert result["wifi_ip"] is None
    assert result["gateway"] is None
    assert result["dns1"] is None


def test_ping_from_device_rejects_invalid_host():
    with patch("adb.network.manager.validate_serial", return_value="s1"):
        result = network.ping_from_device("s1", "; rm -rf /")
    assert result == {"ok": False, "error": "invalid_host"}


def test_ping_from_device_success_builds_command():
    with patch("adb.network.manager.validate_serial", return_value="s1"), \
         patch("adb.network.manager.shell", return_value=("4 packets transmitted", "", 0)) as mock_shell:
        result = network.ping_from_device("s1", "8.8.8.8", count=2)
    assert result["ok"] is True
    assert mock_shell.call_args[0][1] == "ping -c 2 -W 2 8.8.8.8"


def test_validate_port_spec_accepts_valid_and_rejects_invalid():
    assert network._validate_port_spec("tcp:5555") == "tcp:5555"
    assert network._validate_port_spec("udp:53") == "udp:53"
    for bad in ["tcp:70000", "tcp:-1", "http:80", "tcp:", "notaportspec"]:
        with pytest.raises(manager.AdbError):
            network._validate_port_spec(bad)


def test_add_forward_validates_both_specs():
    with pytest.raises(manager.AdbError):
        network.add_forward("s1", "tcp:99999", "tcp:5555")


def test_add_forward_success_and_failure():
    with patch("adb.network.manager.run", return_value=MagicMock(returncode=0, stderr="")):
        result = network.add_forward("s1", "tcp:5555", "tcp:5555")
    assert result == {"ok": True, "error": None}
    with patch("adb.network.manager.run", return_value=MagicMock(returncode=1, stderr="error")):
        result = network.add_forward("s1", "tcp:5555", "tcp:5555")
    assert result == {"ok": False, "error": "error"}


def test_list_forwards_parses_three_column_lines():
    fake_proc = MagicMock(stdout="emulator-5554 tcp:5555 tcp:5555\n")
    with patch("adb.network.manager.run", return_value=fake_proc):
        result = network.list_forwards()
    assert result == [{"serial": "emulator-5554", "local": "tcp:5555", "remote": "tcp:5555"}]


def test_remove_forward_validates_and_runs():
    with pytest.raises(manager.AdbError):
        network.remove_forward("tcp:99999")
    with patch("adb.network.manager.run", return_value=MagicMock(returncode=0)):
        assert network.remove_forward("tcp:5555") == {"ok": True}


def test_list_reverses_parses_three_column_lines():
    fake_proc = MagicMock(stdout="emulator-5554 tcp:9000 tcp:9000\n")
    with patch("adb.network.manager.run", return_value=fake_proc):
        result = network.list_reverses("s1")
    assert result == [{"serial": "emulator-5554", "remote": "tcp:9000", "local": "tcp:9000"}]


def test_add_reverse_validates_and_runs():
    with pytest.raises(manager.AdbError):
        network.add_reverse("s1", "tcp:99999", "tcp:5555")
    with patch("adb.network.manager.run", return_value=MagicMock(returncode=0, stderr="")):
        assert network.add_reverse("s1", "tcp:9000", "tcp:9000") == {"ok": True, "error": None}


def test_remove_reverse_validates_and_runs():
    with pytest.raises(manager.AdbError):
        network.remove_reverse("s1", "tcp:99999")
    with patch("adb.network.manager.run", return_value=MagicMock(returncode=0)):
        assert network.remove_reverse("s1", "tcp:9000") == {"ok": True}
