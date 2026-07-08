from unittest.mock import patch

import pytest

from adb import manager as adb_manager
from adb import root_checker


def test_static_scan_reports_unavailable_when_no_project(tmp_path):
    with patch("adb.root_checker.jadx_manager.project_dir", return_value=tmp_path / "does-not-exist"):
        result = root_checker.static_scan("com.example.app")
    assert result == {"available": False, "reason": "no JADX project decompiled for this package yet", "findings": []}


def test_static_scan_matches_known_root_check_patterns(tmp_path):
    project = tmp_path / "com.example.app"
    project.mkdir()
    (project / "RootCheck.java").write_text(
        'package com.example.app;\n'
        'class RootCheck {\n'
        '  boolean check() {\n'
        '    return new java.io.File("/system/xbin/su").exists();\n'
        '  }\n'
        '  boolean isRooted() { return false; }\n'
        '}\n',
        encoding="utf-8",
    )
    with patch("adb.root_checker.jadx_manager.project_dir", return_value=project):
        result = root_checker.static_scan("com.example.app")
    assert result["available"] is True
    ids = {f["id"] for f in result["findings"]}
    assert "su-path-string" in ids
    assert "root-check-method-name" in ids
    for f in result["findings"]:
        assert f["file"] == "RootCheck.java"
        assert isinstance(f["line"], int)


def test_static_scan_skips_oversized_files(tmp_path):
    project = tmp_path / "com.example.app"
    project.mkdir()
    big = project / "Big.java"
    big.write_text('"/system/xbin/su"' + ("x" * (root_checker._MAX_FILE_BYTES + 10)), encoding="utf-8")
    with patch("adb.root_checker.jadx_manager.project_dir", return_value=project):
        result = root_checker.static_scan("com.example.app")
    assert result["findings"] == []


def test_observe_dynamic_returns_unavailable_on_attach_failure():
    with patch("adb.root_checker.frida_manager.attach", side_effect=adb_manager.AdbError("no frida-server")):
        result = root_checker.observe_dynamic("s1", "com.example.app")
    assert result == {"available": False, "reason": "no frida-server", "events": []}


def test_observe_dynamic_collects_root_check_hits_and_detaches():
    raw_messages = [
        {"message": {"type": "send", "payload": {"type": "notice", "message": "attached"}}},
        {"message": {"type": "send", "payload": {"type": "root_check_hit", "check": "file_exists_su_path", "detail": "/system/xbin/su"}}},
        {"message": {"type": "send", "payload": {"type": "root_check_hit", "check": "package_query_root_app", "detail": "com.topjohnwu.magisk"}}},
    ]
    with patch("adb.root_checker.frida_manager.attach", return_value="sess1") as mock_attach, \
         patch("adb.root_checker.frida_manager.drain_messages", return_value=raw_messages) as mock_drain, \
         patch("adb.root_checker.frida_manager.detach") as mock_detach:
        result = root_checker.observe_dynamic("s1", "com.example.app", duration_sec=3.0)

    mock_attach.assert_called_once_with("s1", {"spawn": "com.example.app"}, root_checker.DYNAMIC_OBSERVER_SCRIPT)
    mock_drain.assert_called_once_with("sess1", 3.0)
    mock_detach.assert_called_once_with("sess1")
    assert result["available"] is True
    assert result["events"] == [
        {"check": "file_exists_su_path", "detail": "/system/xbin/su"},
        {"check": "package_query_root_app", "detail": "com.topjohnwu.magisk"},
    ]


def test_observe_dynamic_detaches_even_if_drain_raises():
    with patch("adb.root_checker.frida_manager.attach", return_value="sess1"), \
         patch("adb.root_checker.frida_manager.drain_messages", side_effect=RuntimeError("boom")), \
         patch("adb.root_checker.frida_manager.detach") as mock_detach:
        with pytest.raises(RuntimeError):
            root_checker.observe_dynamic("s1", "com.example.app")
    mock_detach.assert_called_once_with("sess1")


def test_summarize_verdicts():
    empty = {"findings": []}
    empty_dyn = {"events": []}
    assert root_checker.summarize(empty, empty_dyn)["verdict"] == "no root detection evidence found"

    static_only = {"findings": [{"id": "su-path-string", "file": "A.java", "line": 1}]}
    result = root_checker.summarize(static_only, empty_dyn)
    assert result["verdict"] == "root detection likely implemented"
    assert "static: su-path-string (A.java:1)" in result["matched_indicators"]

    dynamic_only = {"events": [{"check": "file_exists_su_path", "detail": "/sbin/su"}]}
    result = root_checker.summarize(empty, dynamic_only)
    assert result["verdict"] == "root detection likely implemented"
    assert "dynamic: file_exists_su_path (/sbin/su)" in result["matched_indicators"]

    both = root_checker.summarize(static_only, dynamic_only)
    assert both["verdict"] == "root detection implemented (static + dynamic evidence)"


def test_get_report_validates_serial_and_package_first():
    with patch("adb.root_checker.manager.validate_serial", side_effect=adb_manager.AdbError("bad serial")):
        with pytest.raises(adb_manager.AdbError):
            root_checker.get_report("; rm -rf /", "com.example.app")


def test_get_report_skips_dynamic_when_disabled():
    with patch("adb.root_checker.static_scan", return_value={"available": True, "findings": []}) as mock_static, \
         patch("adb.root_checker.observe_dynamic") as mock_dynamic:
        report = root_checker.get_report("s1", "com.example.app", run_dynamic=False)
    mock_static.assert_called_once_with("com.example.app")
    mock_dynamic.assert_not_called()
    assert report["dynamic"] == {"available": False, "reason": "dynamic check skipped", "events": []}
    assert report["verdict"] == "no root detection evidence found"
    assert report["package"] == "com.example.app"
    assert "Play Integrity" not in report["disclaimer"]  # this is the per-app disclaimer, not root_detection's


def test_get_report_runs_dynamic_by_default():
    with patch("adb.root_checker.static_scan", return_value={"available": True, "findings": []}), \
         patch("adb.root_checker.observe_dynamic", return_value={"available": True, "events": []}) as mock_dynamic:
        root_checker.get_report("s1", "com.example.app", dynamic_duration_sec=7.0)
    mock_dynamic.assert_called_once_with("s1", "com.example.app", 7.0)
