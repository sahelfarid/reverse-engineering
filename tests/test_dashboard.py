from unittest.mock import patch

from adb import dashboard


def test_get_cpu_mem_parses_loadavg_and_meminfo():
    loadavg = "0.50 0.40 0.30 1/200 12345"
    meminfo = "MemTotal:        1234567 kB\nMemAvailable:     654321 kB\nOther: 1 kB\n"
    with patch("adb.dashboard.manager.shell") as mock_shell:
        mock_shell.side_effect = [(loadavg, "", 0), (meminfo, "", 0)]
        result = dashboard.get_cpu_mem("serial1")
    assert result["load_1m"] == "0.50"
    assert result["load_5m"] == "0.40"
    assert result["load_15m"] == "0.30"
    assert result["mem_total_kb"] == 1234567
    assert result["mem_available_kb"] == 654321


def test_get_cpu_mem_handles_failed_commands():
    with patch("adb.dashboard.manager.shell") as mock_shell:
        mock_shell.side_effect = [("", "err", 1), ("", "err", 1)]
        result = dashboard.get_cpu_mem("serial1")
    assert result == {
        "load_1m": None, "load_5m": None, "load_15m": None,
        "mem_total_kb": None, "mem_available_kb": None,
    }


def test_get_running_apps_count():
    with patch("adb.dashboard.manager.shell") as mock_shell:
        mock_shell.side_effect = [
            ("package:a\npackage:b\n", "", 0),
            ("package:a\npackage:b\npackage:c\n", "", 0),
        ]
        result = dashboard.get_running_apps_count("serial1")
    assert result == {"user_apps": 2, "total_apps": 3}


def test_get_running_apps_count_handles_failure():
    with patch("adb.dashboard.manager.shell", return_value=("", "err", 1)):
        result = dashboard.get_running_apps_count("serial1")
    assert result == {"user_apps": None, "total_apps": None}


def test_get_screen_status_awake():
    with patch("adb.dashboard.manager.shell", return_value=("mWakefulness=Awake\n", "", 0)):
        assert dashboard.get_screen_status("serial1") == {"screen_on": True}


def test_get_screen_status_asleep_alt_format():
    with patch("adb.dashboard.manager.shell", return_value=("Display Power: state=OFF\n", "", 0)):
        assert dashboard.get_screen_status("serial1") == {"screen_on": False}


def test_get_screen_status_no_match_or_failure():
    with patch("adb.dashboard.manager.shell", return_value=("garbage", "", 0)):
        assert dashboard.get_screen_status("serial1") == {"screen_on": None}
    with patch("adb.dashboard.manager.shell", return_value=("", "err", 1)):
        assert dashboard.get_screen_status("serial1") == {"screen_on": None}


def test_get_foreground_app_parses_component():
    stdout = "  mResumedActivity: ActivityRecord{abc123 u0 com.example.app/com.example.app.MainActivity t1}\n"
    with patch("adb.dashboard.manager.shell", return_value=(stdout, "", 0)):
        result = dashboard.get_foreground_app("serial1")
    assert result == {"package": "com.example.app", "activity": "com.example.app.MainActivity"}


def test_get_foreground_app_no_match_or_empty():
    with patch("adb.dashboard.manager.shell", return_value=("", "", 0)):
        assert dashboard.get_foreground_app("serial1") == {"package": None, "activity": None}
    with patch("adb.dashboard.manager.shell", return_value=("no useful data here", "", 0)):
        assert dashboard.get_foreground_app("serial1") == {"package": None, "activity": None}


def test_get_wifi_status_enabled_disabled_unknown():
    with patch("adb.dashboard.manager.shell", return_value=("mWifiState=enabled\n", "", 0)):
        assert dashboard.get_wifi_status("serial1") == {"enabled": True}
    with patch("adb.dashboard.manager.shell", return_value=("Wi-Fi is disabled\n", "", 0)):
        assert dashboard.get_wifi_status("serial1") == {"enabled": False}
    with patch("adb.dashboard.manager.shell", return_value=("", "err", 1)):
        assert dashboard.get_wifi_status("serial1") == {"enabled": None}


def test_get_overview_composes_all_sections():
    with patch("adb.dashboard.manager.validate_serial", return_value="serial1"), \
         patch("adb.dashboard.get_cpu_mem", return_value={"cpu": True}) as m1, \
         patch("adb.dashboard.get_running_apps_count", return_value={"apps": True}) as m2, \
         patch("adb.dashboard.get_screen_status", return_value={"screen": True}) as m3, \
         patch("adb.dashboard.get_foreground_app", return_value={"fg": True}) as m4, \
         patch("adb.dashboard.get_wifi_status", return_value={"wifi": True}) as m5, \
         patch("adb.dashboard.manager.has_root_shell", return_value=True):
        result = dashboard.get_overview("serial1")
    assert result == {
        "cpu_mem": {"cpu": True},
        "apps": {"apps": True},
        "screen": {"screen": True},
        "foreground": {"fg": True},
        "wifi": {"wifi": True},
        "root_available": True,
    }
    for mock in (m1, m2, m3, m4, m5):
        mock.assert_called_once_with("serial1")
