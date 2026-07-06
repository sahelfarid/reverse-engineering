from unittest.mock import patch

from adb import shell


def test_run_command_empty_command_short_circuits():
    with patch("adb.shell.manager.validate_serial", return_value="serial1"), \
         patch("adb.shell.manager.shell") as mock_shell:
        result = shell.run_command("serial1", "   ")
    assert result == {"stdout": "", "stderr": "", "returncode": 0}
    mock_shell.assert_not_called()


def test_run_command_normal_passes_command_through():
    with patch("adb.shell.manager.validate_serial", return_value="serial1"), \
         patch("adb.shell.manager.shell", return_value=("out", "err", 0)) as mock_shell:
        result = shell.run_command("serial1", "ls /sdcard")
    assert result == {"stdout": "out", "stderr": "err", "returncode": 0}
    assert mock_shell.call_args[0] == ("serial1", "ls /sdcard")


def test_run_command_root_wraps_with_su(monkeypatch):
    monkeypatch.setattr(shell.manager, "quote_remote", lambda v: f"'{v}'")
    with patch("adb.shell.manager.validate_serial", return_value="serial1"), \
         patch("adb.shell.manager.shell", return_value=("out", "", 0)) as mock_shell:
        shell.run_command("serial1", "id", use_su=True)
    remote_cmd = mock_shell.call_args[0][1]
    assert remote_cmd == "su -c 'id'"


def test_run_command_passes_timeout_through():
    with patch("adb.shell.manager.validate_serial", return_value="serial1"), \
         patch("adb.shell.manager.shell", return_value=("", "", 0)) as mock_shell:
        shell.run_command("serial1", "id", timeout=5)
    assert mock_shell.call_args.kwargs["timeout"] == 5


def test_su_available_delegates_to_has_root_shell():
    with patch("adb.shell.manager.has_root_shell", return_value=True) as mock_root:
        assert shell.su_available("serial1") is True
    mock_root.assert_called_once_with("serial1")
