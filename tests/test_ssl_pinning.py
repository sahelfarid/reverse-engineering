from unittest.mock import patch

import pytest

import config
from adb import manager as adb_manager
from adb import ssl_pinning


# --- static_scan ------------------------------------------------------------

def test_static_scan_reports_unavailable_when_no_project(tmp_path):
    with patch("adb.ssl_pinning.jadx_manager.project_dir", return_value=tmp_path / "does-not-exist"):
        result = ssl_pinning.static_scan("com.example.app")
    assert result == {"available": False, "reason": "no JADX project decompiled for this package yet", "findings": []}


def test_static_scan_matches_java_patterns(tmp_path):
    project = tmp_path / "com.example.app"
    project.mkdir()
    (project / "Net.java").write_text(
        'package com.example.app;\n'
        'import okhttp3.CertificatePinner;\n'
        'class Pin implements javax.net.ssl.X509TrustManager {\n'
        '  void check() { CertificatePinner.Builder x; }\n'
        '}\n',
        encoding="utf-8",
    )
    with patch("adb.ssl_pinning.jadx_manager.project_dir", return_value=project):
        result = ssl_pinning.static_scan("com.example.app")
    ids = {f["id"] for f in result["findings"]}
    assert "okhttp-certificate-pinner" in ids
    assert "custom-trust-manager" in ids


def test_static_scan_matches_network_security_config_pin_set(tmp_path):
    project = tmp_path / "com.example.app"
    (project / "res" / "xml").mkdir(parents=True)
    (project / "res" / "xml" / "network_security_config.xml").write_text(
        '<network-security-config><domain-config><pin-set><pin digest="SHA-256">abc=</pin></pin-set></domain-config></network-security-config>',
        encoding="utf-8",
    )
    with patch("adb.ssl_pinning.jadx_manager.project_dir", return_value=project):
        result = ssl_pinning.static_scan("com.example.app")
    ids = {f["id"] for f in result["findings"]}
    assert "network-security-config-pin-set" in ids


def test_static_scan_skips_oversized_files(tmp_path):
    project = tmp_path / "com.example.app"
    project.mkdir()
    big = project / "Big.java"
    big.write_text("CertificatePinner" + ("x" * (ssl_pinning._MAX_FILE_BYTES + 10)), encoding="utf-8")
    with patch("adb.ssl_pinning.jadx_manager.project_dir", return_value=project):
        result = ssl_pinning.static_scan("com.example.app")
    assert result["findings"] == []


# --- observe_dynamic ----------------------------------------------------------

def test_observe_dynamic_returns_unavailable_on_attach_failure():
    with patch("adb.ssl_pinning.frida_manager.attach", side_effect=adb_manager.AdbError("no frida-server")):
        result = ssl_pinning.observe_dynamic("s1", "com.example.app")
    assert result == {"available": False, "reason": "no frida-server", "events": []}


def test_observe_dynamic_collects_hits_and_detaches():
    raw_messages = [
        {"message": {"type": "send", "payload": {"type": "notice", "message": "attached"}}},
        {"message": {"type": "send", "payload": {"type": "pinning_check_hit", "check": "okhttp_certificate_pinner_check", "detail": "example.com"}}},
    ]
    with patch("adb.ssl_pinning.frida_manager.attach", return_value="sess1") as mock_attach, \
         patch("adb.ssl_pinning.frida_manager.drain_messages", return_value=raw_messages) as mock_drain, \
         patch("adb.ssl_pinning.frida_manager.detach") as mock_detach:
        result = ssl_pinning.observe_dynamic("s1", "com.example.app", duration_sec=3.0)

    mock_attach.assert_called_once_with("s1", {"spawn": "com.example.app"}, ssl_pinning.DETECT_OBSERVER_SCRIPT)
    mock_drain.assert_called_once_with("sess1", 3.0)
    mock_detach.assert_called_once_with("sess1")
    assert result["available"] is True
    assert result["events"] == [{"check": "okhttp_certificate_pinner_check", "detail": "example.com"}]


def test_observe_dynamic_detaches_even_if_drain_raises():
    with patch("adb.ssl_pinning.frida_manager.attach", return_value="sess1"), \
         patch("adb.ssl_pinning.frida_manager.drain_messages", side_effect=RuntimeError("boom")), \
         patch("adb.ssl_pinning.frida_manager.detach") as mock_detach:
        with pytest.raises(RuntimeError):
            ssl_pinning.observe_dynamic("s1", "com.example.app")
    mock_detach.assert_called_once_with("sess1")


# --- summarize / get_detection_report -----------------------------------------

def test_summarize_verdicts():
    empty, empty_dyn = {"findings": []}, {"events": []}
    assert ssl_pinning.summarize(empty, empty_dyn)["verdict"] == "no SSL/TLS pinning evidence found"

    static_only = {"findings": [{"id": "okhttp-certificate-pinner", "file": "A.java", "line": 1}]}
    result = ssl_pinning.summarize(static_only, empty_dyn)
    assert result["verdict"] == "SSL/TLS pinning likely implemented"

    dynamic_only = {"events": [{"check": "custom_trust_manager_check", "detail": "com.example.Pin"}]}
    result = ssl_pinning.summarize(empty, dynamic_only)
    assert result["verdict"] == "SSL/TLS pinning likely implemented"

    both = ssl_pinning.summarize(static_only, dynamic_only)
    assert both["verdict"] == "SSL/TLS pinning implemented (static + dynamic evidence)"


def test_get_detection_report_validates_serial_and_package_first():
    with patch("adb.ssl_pinning.manager.validate_serial", side_effect=adb_manager.AdbError("bad serial")):
        with pytest.raises(adb_manager.AdbError):
            ssl_pinning.get_detection_report("; rm -rf /", "com.example.app")


def test_get_detection_report_skips_dynamic_when_disabled():
    with patch("adb.ssl_pinning.static_scan", return_value={"available": True, "findings": []}) as mock_static, \
         patch("adb.ssl_pinning.observe_dynamic") as mock_dynamic:
        report = ssl_pinning.get_detection_report("s1", "com.example.app", run_dynamic=False)
    mock_static.assert_called_once_with("com.example.app")
    mock_dynamic.assert_not_called()
    assert report["dynamic"] == {"available": False, "reason": "dynamic check skipped", "events": []}
    assert report["package"] == "com.example.app"


def test_get_detection_report_runs_dynamic_by_default():
    with patch("adb.ssl_pinning.static_scan", return_value={"available": True, "findings": []}), \
         patch("adb.ssl_pinning.observe_dynamic", return_value={"available": True, "events": []}) as mock_dynamic:
        ssl_pinning.get_detection_report("s1", "com.example.app", dynamic_duration_sec=7.0)
    mock_dynamic.assert_called_once_with("s1", "com.example.app", 7.0)


# --- script store -------------------------------------------------------------

def test_list_scripts_includes_builtin_universal_bypass():
    scripts = ssl_pinning.list_scripts()
    assert "universal-trust-manager-bypass" in scripts
    assert scripts["universal-trust-manager-bypass"]["readonly"] is True


def test_save_and_list_and_delete_custom_script(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)

    result = ssl_pinning.save_script("my-bypass", "console.log('hi');")
    assert result == {"ok": True, "name": "my-bypass"}
    scripts = ssl_pinning.list_scripts()
    assert scripts["my-bypass"]["readonly"] is False
    assert scripts["my-bypass"]["source"] == "console.log('hi');"

    ssl_pinning.delete_script("my-bypass")
    scripts_after = ssl_pinning.list_scripts()
    assert "my-bypass" not in scripts_after


def test_save_script_rejects_overwriting_builtin(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    with pytest.raises(adb_manager.AdbError, match="read-only"):
        ssl_pinning.save_script("universal-trust-manager-bypass", "x")


def test_save_script_rejects_empty_source(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    with pytest.raises(adb_manager.AdbError, match="empty or too large"):
        ssl_pinning.save_script("my-bypass", "")


def test_delete_script_rejects_builtin(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    with pytest.raises(adb_manager.AdbError, match="read-only"):
        ssl_pinning.delete_script("universal-trust-manager-bypass")


def test_delete_script_missing_file_is_a_no_op(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    result = ssl_pinning.delete_script("never-saved")
    assert result == {"ok": True}


# --- attach_bypass -------------------------------------------------------------

def test_attach_bypass_uses_inline_script_source():
    with patch("adb.ssl_pinning.frida_manager.attach", return_value="sess1") as mock_attach:
        result = ssl_pinning.attach_bypass("s1", {"spawn": "com.example.app"}, None, "custom js")
    mock_attach.assert_called_once_with("s1", {"spawn": "com.example.app"}, "custom js")
    assert result["ok"] is True
    assert result["session_id"] == "sess1"
    assert "script_sha256" in result


def test_attach_bypass_resolves_builtin_script_name():
    with patch("adb.ssl_pinning.frida_manager.attach", return_value="sess1") as mock_attach:
        ssl_pinning.attach_bypass("s1", {"pid": 123}, "universal-trust-manager-bypass", None)
    used_source = mock_attach.call_args.args[2]
    assert used_source == ssl_pinning.BYPASS_SCRIPTS["universal-trust-manager-bypass"]["source"]


def test_attach_bypass_raises_for_unknown_script_name():
    with pytest.raises(adb_manager.AdbError, match="script not found"):
        ssl_pinning.attach_bypass("s1", {"pid": 123}, "does-not-exist", None)


def test_attach_bypass_raises_when_no_script_given():
    with pytest.raises(adb_manager.AdbError, match="missing script_source or script_name"):
        ssl_pinning.attach_bypass("s1", {"pid": 123}, None, None)
