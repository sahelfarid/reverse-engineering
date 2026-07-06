from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from adb import apktool_manager
from adb import manager


def _set_dirs(monkeypatch, tmp_path):
    monkeypatch.setattr(apktool_manager, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(apktool_manager, "BUILDS_DIR", tmp_path / "builds")
    monkeypatch.setattr(apktool_manager, "SOURCES_DIR", tmp_path / "sources")
    monkeypatch.setattr(apktool_manager, "APKTOOL_JAR", tmp_path / "vendor" / "apktool" / "apktool.jar")
    monkeypatch.setattr(apktool_manager, "DEBUG_KEYSTORE", tmp_path / "vendor" / "debug.keystore")


def test_project_file_rejects_traversal_absolute_and_symlink_escape(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project = apktool_manager.PROJECTS_DIR / "com.example.app"
    project.mkdir(parents=True)
    (project / "AndroidManifest.xml").write_text("<manifest />", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (project / "escape.txt").symlink_to(outside)

    assert apktool_manager.read_project_file("com.example.app", "AndroidManifest.xml") == "<manifest />"
    for bad in ("../../outside.txt", str(outside), "escape.txt"):
        with pytest.raises(manager.AdbError):
            apktool_manager.read_project_file("com.example.app", bad)


def test_write_project_file_rejects_missing_and_traversal(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project = apktool_manager.PROJECTS_DIR / "com.example.app"
    project.mkdir(parents=True)
    target = project / "res" / "values"
    target.mkdir(parents=True)
    (target / "strings.xml").write_text("<resources />", encoding="utf-8")

    result = apktool_manager.write_project_file("com.example.app", "res/values/strings.xml", "<resources></resources>")
    assert result["ok"] is True
    assert (target / "strings.xml").read_text(encoding="utf-8") == "<resources></resources>"

    with pytest.raises(manager.AdbError):
        apktool_manager.write_project_file("com.example.app", "../escape", "x")
    with pytest.raises(manager.AdbError):
        apktool_manager.write_project_file("com.example.app", "missing.xml", "x")


def test_get_status_reports_missing_java_and_signing(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    with patch("adb.apktool_manager.shutil.which", return_value=None):
        status = apktool_manager.get_status()
    assert status["java"]["installed"] is False
    assert "adoptium" in status["java"]["message"]
    assert status["apktool"]["installed"] is False
    assert status["signing"]["available"] is False
    assert status["debug_keystore"]["present"] is False


def test_get_status_reports_present_tools(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    apktool_manager.APKTOOL_JAR.parent.mkdir(parents=True)
    apktool_manager.APKTOOL_JAR.write_bytes(b"jar")
    apktool_manager.DEBUG_KEYSTORE.parent.mkdir(parents=True, exist_ok=True)
    apktool_manager.DEBUG_KEYSTORE.write_bytes(b"keystore")
    with patch("adb.apktool_manager.java_status", return_value={"installed": True, "path": "/bin/java", "version": "java 17"}), \
         patch("adb.apktool_manager.apktool_version", return_value="3.0.2"), \
         patch("adb.apktool_manager.signing_tools_status", return_value={"available": True, "preferred": "apksigner", "apksigner": "/sdk/apksigner", "zipalign": None, "jarsigner": None, "keytool": "/bin/keytool"}):
        status = apktool_manager.get_status()
    assert status["java"]["installed"] is True
    assert status["apktool"]["installed"] is True
    assert status["apktool"]["version"] == "3.0.2"
    assert status["signing"]["preferred"] == "apksigner"
    assert status["debug_keystore"]["present"] is True


def _fake_streaming_response(body: bytes):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.iter_content = MagicMock(return_value=[body])
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_ensure_apktool_downloads_to_vendor(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(apktool_manager.config, "TEMP_DIR", tmp_path / "temp")
    apktool_manager.config.TEMP_DIR.mkdir()
    with patch("adb.apktool_manager.requests.get", return_value=_fake_streaming_response(b"jar-bytes")) as mock_get:
        path = apktool_manager.ensure_apktool()
    assert path == apktool_manager.APKTOOL_JAR
    assert path.read_bytes() == b"jar-bytes"
    assert mock_get.call_args.kwargs["stream"] is True


def test_ensure_apktool_raises_on_download_failure(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(apktool_manager.config, "TEMP_DIR", tmp_path)
    with patch("adb.apktool_manager.requests.get", side_effect=requests.RequestException("down")):
        with pytest.raises(manager.AdbError, match="Failed to download apktool"):
            apktool_manager.ensure_apktool()


def test_rebuild_pipeline_uses_list_argv_for_apktool_zipalign_and_apksigner(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project = apktool_manager.PROJECTS_DIR / "com.example.app"
    project.mkdir(parents=True)
    jar = tmp_path / "apktool.jar"
    jar.write_bytes(b"jar")

    def fake_run(args, timeout=None):
        if args[:3] == ["/bin/java", "-jar", str(jar)]:
            out = Path(args[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"unsigned")
        elif args[0] == "/sdk/zipalign":
            Path(args[-1]).write_bytes(b"aligned")
        elif args[0] == "/sdk/apksigner":
            Path(args[args.index("--out") + 1]).write_bytes(b"signed")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("adb.apktool_manager.java_status", return_value={"installed": True, "path": "/bin/java", "version": "java"}), \
         patch("adb.apktool_manager.ensure_apktool", return_value=jar), \
         patch("adb.apktool_manager.signing_tools_status", return_value={"apksigner": "/sdk/apksigner", "zipalign": "/sdk/zipalign", "jarsigner": None, "keytool": "/bin/keytool"}), \
         patch("adb.apktool_manager.ensure_debug_keystore", return_value=tmp_path / "debug.keystore"), \
         patch("adb.apktool_manager._run_tool", side_effect=fake_run) as mock_run:
        signed = apktool_manager.rebuild("com.example.app")

    calls = [call.args[0] for call in mock_run.call_args_list]
    assert calls[0] == ["/bin/java", "-jar", str(jar), "b", str(project), "-o", str(apktool_manager.BUILDS_DIR / "com.example.app" / "rebuilt-unsigned.apk")]
    assert calls[1][0] == "/sdk/zipalign"
    assert calls[2][0:2] == ["/sdk/apksigner", "sign"]
    assert signed.read_bytes() == b"signed"
