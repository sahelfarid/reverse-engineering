from unittest.mock import patch

from adb.process_manager import list_processes


def test_list_processes_parses_named_columns():
    sample = "USER  PID  PPID  RSS  NAME\nroot  1  0  1000  init\nu0_a123  4567  789  50000  com.example.app\n"
    with patch("adb.process_manager.manager.shell", return_value=(sample, "", 0)):
        result = list_processes("emulator-5554")
    assert result["parseable"] is True
    assert result["processes"][0]["pid"] == 1
    assert result["processes"][0]["name"] == "init"
    assert result["processes"][1]["name"] == "com.example.app"
    assert result["processes"][1]["rss_kb"] == "50000"


def test_list_processes_handles_empty_output():
    with patch("adb.process_manager.manager.shell", return_value=("", "", 1)):
        result = list_processes("emulator-5554")
    assert result["processes"] == []
    assert result["parseable"] is False
