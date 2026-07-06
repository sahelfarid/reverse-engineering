from unittest.mock import patch

from adb import battery

SAMPLE_DUMPSYS_BATTERY = """Current Battery Service state:
  AC powered: false
  USB powered: true
  level: 85
  status: 2
  health: 2
  voltage: 4123
  technology: Li-ion
  cycle count: 42
"""


def test_get_battery_detail_merges_basic_and_dumpsys_fields():
    with patch("adb.battery.devices.get_battery_info", return_value={"level": 85, "status": "2"}), \
         patch("adb.battery.manager.shell", return_value=(SAMPLE_DUMPSYS_BATTERY, "", 0)):
        result = battery.get_battery_detail("s1")
    assert result["level"] == 85
    assert result["voltage_mv"] == "4123"
    assert result["technology"] == "Li-ion"
    assert result["cycle_count"] == "42"


def test_get_battery_detail_handles_dumpsys_failure():
    with patch("adb.battery.devices.get_battery_info", return_value={"level": None}), \
         patch("adb.battery.manager.shell", return_value=("", "err", 1)):
        result = battery.get_battery_detail("s1")
    assert result["voltage_mv"] is None
    assert result["technology"] is None
    assert result["cycle_count"] is None


def test_get_cpu_info_parses_cores_hardware_and_model():
    sample = (
        "processor\t: 0\nmodel name\t: ARMv8\nHardware\t: Qualcomm Technologies, Inc SM8350\n"
        "processor\t: 1\nmodel name\t: ARMv8\nHardware\t: Qualcomm Technologies, Inc SM8350\n"
    )
    with patch("adb.battery.manager.shell", return_value=(sample, "", 0)):
        result = battery.get_cpu_info("s1")
    assert result["cores"] == 2
    assert result["hardware"] == "Qualcomm Technologies, Inc SM8350"
    assert result["model"] == "ARMv8"


def test_get_cpu_info_empty_on_failure():
    with patch("adb.battery.manager.shell", return_value=("", "err", 1)):
        assert battery.get_cpu_info("s1") == {"cores": None, "hardware": None, "model": None}


def test_get_gpu_info_parses_egl_and_renderer():
    with patch("adb.battery.manager.shell") as mock_shell:
        mock_shell.side_effect = [
            ("adreno\n", "", 0),
            ("GLES: Qualcomm, Adreno (TM) 660, OpenGL ES 3.2\n", "", 0),
        ]
        result = battery.get_gpu_info("s1")
    assert result["egl"] == "adreno"
    assert "Adreno" in result["renderer"]


def test_get_gpu_info_none_on_failure():
    with patch("adb.battery.manager.shell", return_value=("", "err", 1)):
        result = battery.get_gpu_info("s1")
    assert result == {"egl": None, "renderer": None}


def test_get_sensors_parses_quoted_names():
    sample = 'Sensor 0: name="Accelerometer" vendor="Bosch"\nSensor 1: name="Gyroscope" vendor="Bosch"\n'
    with patch("adb.battery.manager.shell", return_value=(sample, "", 0)):
        result = battery.get_sensors("s1")
    assert result == ["Accelerometer", "Gyroscope"]


def test_get_sensors_falls_back_to_numbered_format():
    sample = "0) Accelerometer, vendor: Bosch, version: 1\n1) Gyroscope, vendor: Bosch, version: 1\n"
    with patch("adb.battery.manager.shell", return_value=(sample, "", 0)):
        result = battery.get_sensors("s1")
    assert result == ["Accelerometer", "Gyroscope"]


def test_get_sensors_empty_on_failure():
    with patch("adb.battery.manager.shell", return_value=("", "err", 1)):
        assert battery.get_sensors("s1") == []


def test_get_disk_usage_parses_df_output():
    sample = (
        "Filesystem  Size  Used Avail Use% Mounted on\n"
        "/dev/block/dm-1  100G   40G   60G  40% /data\n"
    )
    with patch("adb.battery.manager.shell", return_value=(sample, "", 0)):
        result = battery.get_disk_usage("s1")
    assert result == [{
        "filesystem": "/dev/block/dm-1", "size": "100G", "used": "40G",
        "available": "60G", "use_pct": "40%", "mounted_on": "/data",
    }]


def test_get_disk_usage_empty_on_failure():
    with patch("adb.battery.manager.shell", return_value=("", "err", 1)):
        assert battery.get_disk_usage("s1") == []


def test_get_hardware_detail_composes_all_sections():
    with patch("adb.battery.manager.validate_serial", return_value="s1"), \
         patch("adb.battery.get_battery_detail", return_value={"level": 1}) as m1, \
         patch("adb.battery.get_cpu_info", return_value={"cores": 8}) as m2, \
         patch("adb.battery.get_gpu_info", return_value={"egl": "x"}) as m3, \
         patch("adb.battery.get_sensors", return_value=["Accelerometer"]) as m4, \
         patch("adb.battery.get_disk_usage", return_value=[]) as m5:
        result = battery.get_hardware_detail("s1")
    assert result == {
        "battery": {"level": 1}, "cpu": {"cores": 8}, "gpu": {"egl": "x"},
        "sensors": ["Accelerometer"], "disk": [],
    }
    for mock in (m1, m2, m3, m4, m5):
        mock.assert_called_once_with("s1")
