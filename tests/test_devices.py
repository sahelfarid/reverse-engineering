import subprocess
from unittest.mock import MagicMock, patch

from adb import devices
from adb.devices import _parse_devices_line


def test_parse_devices_line_authorized_usb():
    entry = _parse_devices_line(
        "R3CN30XXXX      device usb:1-1 product:redfin model:Pixel_5 device:redfin transport_id:1"
    )
    assert entry["serial"] == "R3CN30XXXX"
    assert entry["state"] == "device"
    assert entry["model"] == "Pixel_5"
    assert entry["transport_id"] == "1"
    assert entry["is_wireless"] is False


def test_parse_devices_line_unauthorized():
    entry = _parse_devices_line("R3CN30XXXX      unauthorized usb:1-1 transport_id:1")
    assert entry["state"] == "unauthorized"
    assert entry["model"] is None


def test_parse_devices_line_wireless():
    entry = _parse_devices_line("192.168.1.50:5555 device product:x model:y device:z transport_id:4")
    assert entry["is_wireless"] is True
    assert entry["serial"] == "192.168.1.50:5555"


def test_parse_devices_line_header_and_blank_ignored():
    assert _parse_devices_line("List of devices attached") is None
    assert _parse_devices_line("") is None
    assert _parse_devices_line("   ") is None


def test_list_devices_parses_run_output():
    fake_proc = MagicMock(stdout="List of devices attached\nR3CN30XXXX      device usb:1-1 product:redfin model:Pixel_5 device:redfin transport_id:1\n\n")
    with patch("adb.devices.manager.run", return_value=fake_proc) as mock_run:
        entries = devices.list_devices()
    assert len(entries) == 1
    assert entries[0]["serial"] == "R3CN30XXXX"
    assert mock_run.call_args[0][0] == ["devices", "-l"]


def test_list_fastboot_devices_returns_empty_when_fastboot_missing():
    with patch("adb.devices.fastboot_path", return_value=None):
        assert devices.list_fastboot_devices() == []


def test_list_fastboot_devices_parses_output(tmp_path):
    fake_fastboot = tmp_path / "fastboot"
    fake_fastboot.write_text("fake")
    fake_proc = MagicMock(stdout="ABC123\tfastboot\n\n")
    with patch("adb.devices.fastboot_path", return_value=fake_fastboot), \
         patch("adb.devices.subprocess.run", return_value=fake_proc) as mock_run:
        entries = devices.list_fastboot_devices()
    assert entries == [{
        "serial": "ABC123", "state": "fastboot", "product": None,
        "model": None, "device": None, "transport_id": None, "is_wireless": False,
    }]
    assert mock_run.call_args[0][0] == [str(fake_fastboot), "devices"]


def test_list_fastboot_devices_handles_timeout(tmp_path):
    fake_fastboot = tmp_path / "fastboot"
    fake_fastboot.write_text("fake")
    with patch("adb.devices.fastboot_path", return_value=fake_fastboot), \
         patch("adb.devices.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="fastboot", timeout=10)):
        assert devices.list_fastboot_devices() == []


def test_get_basic_properties_reads_each_prop():
    with patch("adb.devices.manager.shell") as mock_shell:
        mock_shell.side_effect = [
            ("Pixel 5", "", 0), ("Google", "", 0), ("13", "", 0),
            ("33", "", 0), ("arm64-v8a", "", 0), ("google/redfin/redfin", "", 0),
        ]
        result = devices.get_basic_properties("serial1")
    assert result["model"] == "Pixel 5"
    assert result["manufacturer"] == "Google"
    assert result["sdk_version"] == "33"


def test_get_basic_properties_none_on_failure():
    with patch("adb.devices.manager.shell", return_value=("", "err", 1)):
        result = devices.get_basic_properties("serial1")
    assert all(value is None for value in result.values())


def test_get_battery_info_parses_dumpsys():
    stdout = (
        "level: 80\n"
        "status: 2\n"
        "health: 2\n"
        "temperature: 250\n"
        "AC powered: false\n"
        "USB powered: true\n"
    )
    with patch("adb.devices.manager.shell", return_value=(stdout, "", 0)):
        result = devices.get_battery_info("serial1")
    assert result["level"] == 80
    assert result["temperature_c"] == 25.0
    assert result["charging"] is True


def test_get_battery_info_defaults_on_failure():
    with patch("adb.devices.manager.shell", return_value=("", "err", 1)):
        result = devices.get_battery_info("serial1")
    assert result == {"level": None, "status": None, "health": None, "temperature_c": None, "charging": None}


def test_get_storage_info_parses_df_output():
    stdout = (
        "Filesystem     1K-blocks    Used Available Use% Mounted on\n"
        "/dev/block/dm-1  10000000 4000000   6000000  40% /data\n"
    )
    with patch("adb.devices.manager.shell", return_value=(stdout, "", 0)):
        result = devices.get_storage_info("serial1")
    assert result["volumes"] == [{
        "filesystem": "/dev/block/dm-1", "size_kb": "10000000", "used_kb": "4000000",
        "available_kb": "6000000", "use_pct": "40%", "mounted_on": "/data",
    }]


def test_get_storage_info_empty_on_failure():
    with patch("adb.devices.manager.shell", return_value=("", "err", 1)):
        assert devices.get_storage_info("serial1") == {"volumes": []}


def test_get_device_detail_composes_sections():
    with patch("adb.devices.manager.validate_serial", return_value="serial1"), \
         patch("adb.devices.get_basic_properties", return_value={"model": "x"}), \
         patch("adb.devices.get_battery_info", return_value={"level": 1}), \
         patch("adb.devices.get_storage_info", return_value={"volumes": []}), \
         patch("adb.devices.is_root_available", return_value=True):
        detail = devices.get_device_detail("serial1")
    assert detail["serial"] == "serial1"
    assert detail["properties"] == {"model": "x"}
    assert detail["root_available"] is True
