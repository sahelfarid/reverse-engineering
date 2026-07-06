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
