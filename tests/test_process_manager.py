from unittest.mock import patch

from adb import process_manager
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


def test_list_processes_falls_back_to_plain_ps_a():
    fallback_sample = "PID   USER     VSZ   STAT COMMAND\n1     root     123   S    init\n"
    with patch("adb.process_manager.manager.shell") as mock_shell:
        mock_shell.side_effect = [("", "not supported", 1), (fallback_sample, "", 0)]
        result = list_processes("emulator-5554")
    assert result["parseable"] is True
    assert result["processes"][0]["name"] == "init"
    assert mock_shell.call_count == 2


def test_list_processes_marks_short_rows_unparseable():
    sample = "USER  PID  PPID  RSS  NAME\nroot  1  0  1000  init\ntruncated_row\n"
    with patch("adb.process_manager.manager.shell", return_value=(sample, "", 0)):
        result = list_processes("emulator-5554")
    assert result["parseable"] is False
    assert len(result["processes"]) == 1  # the truncated row is skipped


def test_list_processes_sorts_by_pid_with_none_last():
    sample = "USER  PID  PPID  RSS  NAME\nroot  50  0  1000  b\nroot  10  0  1000  a\n"
    with patch("adb.process_manager.manager.shell", return_value=(sample, "", 0)):
        result = list_processes("emulator-5554")
    assert [p["pid"] for p in result["processes"]] == [10, 50]


def test_kill_process_success():
    with patch("adb.process_manager.manager.shell", return_value=("", "", 0)) as mock_shell:
        result = process_manager.kill_process("s1", 1234)
    assert result == {"ok": True}
    assert mock_shell.call_args[0][1] == "kill -TERM 1234"


def test_kill_process_sanitizes_signal_name():
    with patch("adb.process_manager.manager.shell", return_value=("", "", 0)) as mock_shell:
        process_manager.kill_process("s1", 1234, sig="sigkill; rm -rf /")
    assert mock_shell.call_args[0][1] == "kill -SIGKILLRMRF 1234"


def test_kill_process_empty_signal_defaults_to_term():
    with patch("adb.process_manager.manager.shell", return_value=("", "", 0)) as mock_shell:
        process_manager.kill_process("s1", 1234, sig=";;;")
    assert mock_shell.call_args[0][1] == "kill -TERM 1234"


def test_kill_process_falls_back_to_root_on_failure():
    with patch("adb.process_manager.manager.shell") as mock_shell, \
         patch("adb.process_manager.manager.has_root_shell", return_value=True):
        mock_shell.side_effect = [("", "permission denied", 1), ("", "", 0)]
        result = process_manager.kill_process("s1", 1234)
    assert result == {"ok": True, "used_root": True}
    assert mock_shell.call_args_list[1].args[1] == "su 0 kill -TERM 1234"


def test_kill_process_root_fallback_also_fails():
    with patch("adb.process_manager.manager.shell") as mock_shell, \
         patch("adb.process_manager.manager.has_root_shell", return_value=True):
        mock_shell.side_effect = [("", "permission denied", 1), ("", "still denied", 1)]
        result = process_manager.kill_process("s1", 1234)
    assert result == {"ok": False, "error": "still denied"}


def test_kill_process_permission_denied_without_root():
    with patch("adb.process_manager.manager.shell", return_value=("", "", 1)), \
         patch("adb.process_manager.manager.has_root_shell", return_value=False):
        result = process_manager.kill_process("s1", 1234)
    assert result == {"ok": False, "error": "permission_denied (try a rooted device)"}


def test_kill_process_accepts_string_pid():
    with patch("adb.process_manager.manager.shell", return_value=("", "", 0)) as mock_shell:
        process_manager.kill_process("s1", "1234")
    assert mock_shell.call_args[0][1] == "kill -TERM 1234"
