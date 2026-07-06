from unittest.mock import MagicMock, patch

import pytest

from adb import logcat, manager
from adb.logcat import parse_logcat_line


def test_parse_logcat_line_threadtime_format():
    line = "07-06 17:50:12.345  1234  1234 I ActivityManager: Displayed com.example/.MainActivity"
    entry = parse_logcat_line(line)
    assert entry["parseable"] is True
    assert entry["level"] == "I"
    assert entry["tag"] == "ActivityManager"
    assert entry["pid"] == "1234"
    assert entry["message"] == "Displayed com.example/.MainActivity"


def test_parse_logcat_line_garbled_fallback():
    entry = parse_logcat_line("not a logcat line")
    assert entry["parseable"] is False
    assert entry["level"] is None
    assert entry["raw"] == "not a logcat line"


def test_parse_logcat_line_error_level():
    line = "07-06 17:50:13.000  555  556 E MyTag: something broke"
    entry = parse_logcat_line(line)
    assert entry["level"] == "E"
    assert entry["tag"] == "MyTag"


def test_resolve_pid_success_and_failure():
    with patch("adb.logcat.manager.shell", return_value=("1234\n", "", 0)):
        assert logcat.resolve_pid("s1", "com.example.app") == "1234"
    with patch("adb.logcat.manager.shell", return_value=("", "", 1)):
        assert logcat.resolve_pid("s1", "com.example.app") is None
    with patch("adb.logcat.manager.shell", return_value=("", "", 0)):
        assert logcat.resolve_pid("s1", "com.example.app") is None


def test_clear_logcat_success_and_failure():
    with patch("adb.logcat.manager.run", return_value=MagicMock(returncode=0)):
        assert logcat.clear_logcat("s1") == {"ok": True}
    with patch("adb.logcat.manager.run", return_value=MagicMock(returncode=1)):
        assert logcat.clear_logcat("s1") == {"ok": False}


def _make_fake_process(lines):
    proc = MagicMock()
    proc.stdout = iter(lines)
    proc.wait = MagicMock()
    return proc


def test_stream_logcat_yields_parsed_entries():
    lines = [
        "07-06 17:50:12.345  1234  1234 I ActivityManager: hello\n",
        "07-06 17:50:13.000  555  556 E MyTag: broke\n",
    ]
    fake_proc = _make_fake_process(lines)
    with patch("adb.logcat.manager.validate_serial", return_value="s1"), \
         patch("adb.logcat.manager.find_adb", return_value=manager.Path("/usr/bin/adb")), \
         patch("adb.logcat.subprocess.Popen", return_value=fake_proc):
        entries = list(logcat.stream_logcat("s1", None, None, None, None))
    assert len(entries) == 2
    fake_proc.terminate.assert_called_once()


def test_stream_logcat_filters_by_tag_pid_and_level():
    lines = [
        "07-06 17:50:12.345  1234  1234 I WantedTag: keep me\n",
        "07-06 17:50:12.345  9999  9999 I OtherTag: drop me\n",
        "07-06 17:50:12.345  1234  1234 D WantedTag: too low level\n",
    ]
    fake_proc = _make_fake_process(lines)
    with patch("adb.logcat.manager.validate_serial", return_value="s1"), \
         patch("adb.logcat.manager.find_adb", return_value=manager.Path("/usr/bin/adb")), \
         patch("adb.logcat.subprocess.Popen", return_value=fake_proc):
        entries = list(logcat.stream_logcat("s1", "WantedTag", "1234", "I", None))
    assert len(entries) == 1
    assert entries[0]["message"] == "keep me"


def test_stream_logcat_filters_by_query_regex():
    lines = [
        "07-06 17:50:12.345  1234  1234 I Tag: needle here\n",
        "07-06 17:50:12.345  1234  1234 I Tag: nothing relevant\n",
    ]
    fake_proc = _make_fake_process(lines)
    with patch("adb.logcat.manager.validate_serial", return_value="s1"), \
         patch("adb.logcat.manager.find_adb", return_value=manager.Path("/usr/bin/adb")), \
         patch("adb.logcat.subprocess.Popen", return_value=fake_proc):
        entries = list(logcat.stream_logcat("s1", None, None, None, "needle"))
    assert len(entries) == 1
    assert "needle" in entries[0]["message"]


def test_stream_logcat_raises_adb_error_on_invalid_regex():
    with patch("adb.logcat.manager.validate_serial", return_value="s1"), \
         patch("adb.logcat.manager.find_adb", return_value=manager.Path("/usr/bin/adb")):
        with pytest.raises(manager.AdbError, match="invalid regex"):
            list(logcat.stream_logcat("s1", None, None, None, "("))  # unbalanced paren


def test_stream_logcat_raises_when_adb_not_installed():
    with patch("adb.logcat.manager.validate_serial", return_value="s1"), \
         patch("adb.logcat.manager.find_adb", return_value=None):
        with pytest.raises(manager.AdbNotInstalledError):
            list(logcat.stream_logcat("s1", None, None, None, None))


def test_stream_logcat_terminates_process_on_early_break():
    lines = ["07-06 17:50:12.345  1234  1234 I Tag: one\n", "07-06 17:50:12.345  1234  1234 I Tag: two\n"]
    fake_proc = _make_fake_process(lines)
    with patch("adb.logcat.manager.validate_serial", return_value="s1"), \
         patch("adb.logcat.manager.find_adb", return_value=manager.Path("/usr/bin/adb")), \
         patch("adb.logcat.subprocess.Popen", return_value=fake_proc):
        gen = logcat.stream_logcat("s1", None, None, None, None)
        next(gen)
        gen.close()
    fake_proc.terminate.assert_called_once()
