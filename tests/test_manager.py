from unittest.mock import MagicMock, patch

import pytest

from adb import manager


def test_quote_remote_escapes_shell_metacharacters():
    assert manager.quote_remote("hello world") == "'hello world'"
    quoted = manager.quote_remote("a; rm -rf /")
    assert quoted.startswith("'") and quoted.endswith("'")
    assert "; rm -rf /" in quoted  # stays inside quotes, doesn't terminate them


def test_validate_serial_accepts_normal_and_wireless_serials():
    assert manager.validate_serial("R3CN30ABCDE") == "R3CN30ABCDE"
    assert manager.validate_serial("192.168.1.5:5555") == "192.168.1.5:5555"


def test_validate_serial_rejects_shell_metacharacters():
    for bad in ["; rm -rf /", "a`whoami`", "a$(whoami)", "a && b", ""]:
        with pytest.raises(manager.AdbError):
            manager.validate_serial(bad)


def test_shell_parses_sentinel_exit_code():
    fake_proc = MagicMock(stdout="hello\n__RC__:0\n", stderr="", returncode=0)
    with patch("adb.manager.run", return_value=fake_proc) as mock_run:
        stdout, stderr, rc = manager.shell("emulator-5554", "echo hello")
    assert stdout == "hello"
    assert rc == 0
    args = mock_run.call_args[0][0]
    assert args[:3] == ["-s", "emulator-5554", "shell"]
    assert "echo hello" in args[-1]
    assert "__RC__:$?" in args[-1]


def test_shell_parses_nonzero_exit_code():
    fake_proc = MagicMock(stdout="oops\n__RC__:127\n", stderr="not found", returncode=0)
    with patch("adb.manager.run", return_value=fake_proc):
        stdout, stderr, rc = manager.shell("emulator-5554", "badcmd")
    assert stdout == "oops"
    assert rc == 127


def test_find_adb_prefers_vendor_over_system(tmp_path, monkeypatch):
    vendor_adb = tmp_path / "platform-tools" / ("adb.exe" if manager.os.name == "nt" else "adb")
    vendor_adb.parent.mkdir(parents=True)
    vendor_adb.write_text("fake")

    monkeypatch.setattr(manager.config, "VENDOR_DIR", tmp_path)
    monkeypatch.setattr(manager.config, "load_settings", lambda: {"adb_path_override": None})
    found = manager.find_adb()
    assert found == vendor_adb
