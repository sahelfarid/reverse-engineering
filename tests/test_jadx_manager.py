from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from adb import jadx_manager
from adb import jobs
from adb import manager


def _set_dirs(monkeypatch, tmp_path):
    monkeypatch.setattr(jadx_manager, "JADX_DIR", tmp_path / "vendor" / "jadx")
    monkeypatch.setattr(jadx_manager, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(jadx_manager, "SOURCES_DIR", tmp_path / "sources")
    monkeypatch.setattr(jadx_manager, "FINDINGS_DIR", tmp_path / "findings")
    monkeypatch.setattr(jadx_manager, "REPORTS_DIR", tmp_path / "reports")


def _write_manifest(project_root, **overrides):
    values = {
        "min_sdk": "21", "target_sdk": "34", "debuggable": "true", "allow_backup": "true",
    }
    values.update(overrides)
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "AndroidManifest.xml").write_text(f'''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.example.app">
  <uses-sdk android:minSdkVersion="{values['min_sdk']}" android:targetSdkVersion="{values['target_sdk']}"/>
  <uses-permission android:name="android.permission.CAMERA"/>
  <application android:debuggable="{values['debuggable']}" android:allowBackup="{values['allow_backup']}">
    <activity android:name=".MainActivity" android:exported="true">
      <intent-filter><action android:name="android.intent.action.MAIN"/></intent-filter>
    </activity>
  </application>
</manifest>''', encoding="utf-8")


# --- path safety --------------------------------------------------------------

def test_read_project_file_rejects_traversal_absolute_and_symlink_escape(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project = jadx_manager.PROJECTS_DIR / "com.example.app"
    project.mkdir(parents=True)
    (project / "AndroidManifest.xml").write_text("<manifest />", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (project / "escape.txt").symlink_to(outside)

    assert jadx_manager.read_project_file("com.example.app", "AndroidManifest.xml") == "<manifest />"
    for bad in ("../../outside.txt", str(outside), "escape.txt"):
        with pytest.raises(manager.AdbError):
            jadx_manager.read_project_file("com.example.app", bad)


def test_search_project_rejects_traversal_project_path(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project = jadx_manager.PROJECTS_DIR / "com.example.app"
    project.mkdir(parents=True)
    (project / "A.java").write_text("class A { String s = \"needle\"; }", encoding="utf-8")

    with pytest.raises(manager.AdbError):
        jadx_manager.search_project("../../etc", "needle")
    with pytest.raises(manager.AdbError):
        jadx_manager.search_project("com.example.app/../../etc", "needle")


# --- status / tool discovery ---------------------------------------------------

def test_get_status_reports_missing_java(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    with patch("adb.jadx_manager.apktool_manager.shutil.which", return_value=None), \
         patch("adb.jadx_manager.find_jadx", return_value=None):
        status = jadx_manager.get_status()
    assert status["java"]["installed"] is False
    assert "adoptium" in status["java"]["message"]
    assert status["jadx"]["installed"] is False
    assert status["jadx"]["version"] is None


def test_get_status_reports_present_tools(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    launcher = jadx_manager._vendor_launcher_path()
    with patch("adb.jadx_manager.java_status", return_value={"installed": True, "path": "/bin/java", "version": "java 17"}), \
         patch("adb.jadx_manager.find_jadx", return_value=launcher), \
         patch("adb.jadx_manager.jadx_version", return_value="jadx 1.5.1"):
        status = jadx_manager.get_status()
    assert status["java"]["installed"] is True
    assert status["jadx"]["installed"] is True
    assert status["jadx"]["version"] == "jadx 1.5.1"
    assert status["jadx"]["source"] == "vendor"
    assert status["jadx"]["pinned_version"] == jadx_manager.config.JADX_VERSION


def test_find_jadx_resolution_order_override_then_path_then_vendor(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    vendor = jadx_manager._vendor_launcher_path()
    vendor.parent.mkdir(parents=True)
    vendor.write_text("#!/bin/sh\n", encoding="utf-8")

    # Only vendor present -> vendor wins.
    with patch("adb.jadx_manager._jadx_path_override", return_value=None), \
         patch("adb.jadx_manager.shutil.which", return_value=None):
        assert jadx_manager.find_jadx() == vendor

    # System jadx on PATH beats the vendor install.
    with patch("adb.jadx_manager._jadx_path_override", return_value=None), \
         patch("adb.jadx_manager.shutil.which", return_value="/usr/local/bin/jadx"):
        assert jadx_manager.find_jadx() == Path("/usr/local/bin/jadx")

    # An explicit override beats everything else.
    override_path = tmp_path / "custom" / "jadx"
    override_path.parent.mkdir(parents=True)
    override_path.write_text("#!/bin/sh\n", encoding="utf-8")
    with patch("adb.jadx_manager._jadx_path_override", return_value=str(override_path)), \
         patch("adb.jadx_manager.shutil.which", return_value="/usr/local/bin/jadx"):
        assert jadx_manager.find_jadx() == override_path


def test_jadx_version_returns_none_on_nonzero_exit(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    with patch("adb.jadx_manager.subprocess.run", return_value=MagicMock(returncode=1, stdout="", stderr="broken JAVA_HOME")):
        assert jadx_manager.jadx_version(Path("/opt/homebrew/bin/jadx")) is None


# --- ensure_jadx / install ------------------------------------------------------

def _fake_streaming_response(body: bytes):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.iter_content = MagicMock(return_value=[body])
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _make_zip_bytes(members: dict) -> bytes:
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_ensure_jadx_skips_download_when_already_resolvable(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    existing = Path("/usr/local/bin/jadx")
    with patch("adb.jadx_manager.find_jadx", return_value=existing), \
         patch("adb.jadx_manager.requests.get") as mock_get:
        result = jadx_manager.ensure_jadx()
    assert result == existing
    mock_get.assert_not_called()


def test_ensure_jadx_downloads_and_extracts_when_missing(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(jadx_manager.config, "TEMP_DIR", tmp_path / "temp")
    jadx_manager.config.TEMP_DIR.mkdir()
    zip_bytes = _make_zip_bytes({f"bin/{jadx_manager._launcher_name()}": "#!/bin/sh\necho jadx\n"})
    with patch("adb.jadx_manager.find_jadx", return_value=None), \
         patch("adb.jadx_manager.requests.get", return_value=_fake_streaming_response(zip_bytes)):
        launcher = jadx_manager.ensure_jadx()
    assert launcher == jadx_manager._vendor_launcher_path()
    assert launcher.is_file()


def test_ensure_jadx_rejects_zip_slip_member(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(jadx_manager.config, "TEMP_DIR", tmp_path / "temp")
    jadx_manager.config.TEMP_DIR.mkdir()
    zip_bytes = _make_zip_bytes({"../../evil.sh": "rm -rf /"})
    with patch("adb.jadx_manager.find_jadx", return_value=None), \
         patch("adb.jadx_manager.requests.get", return_value=_fake_streaming_response(zip_bytes)):
        with pytest.raises(jadx_manager.JadxError):
            jadx_manager.ensure_jadx()


def test_ensure_jadx_raises_on_download_failure(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(jadx_manager.config, "TEMP_DIR", tmp_path)
    with patch("adb.jadx_manager.find_jadx", return_value=None), \
         patch("adb.jadx_manager.requests.get", side_effect=requests.RequestException("down")):
        with pytest.raises(jadx_manager.JadxError, match="Failed to download jadx"):
            jadx_manager.ensure_jadx()


# --- decompile core (mocked subprocess) -----------------------------------------

class _FakeProcess:
    def __init__(self, lines, returncode=0):
        self.stdout = iter(lines)
        self.returncode = returncode
        self.terminated = False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        pass


def test_run_decompile_treats_nonzero_exit_with_output_as_success(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project_root = jadx_manager.PROJECTS_DIR / "com.example.app"

    def make_output(*_a, **_kw):
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "A.java").write_text("class A {}", encoding="utf-8")
        return _FakeProcess(["partial failure\n"], returncode=1)

    with patch("adb.jadx_manager.java_status", return_value={"installed": True, "path": "/bin/java", "message": None}), \
         patch("adb.jadx_manager.ensure_jadx", return_value=Path("/opt/jadx/bin/jadx")), \
         patch("adb.jadx_manager.subprocess.Popen", side_effect=make_output) as mock_popen:
        message = jadx_manager._run_decompile(
            Path("/tmp/fake.apk"), project_root, None, no_res=False, deobf=False, show_bad_code=True,
        )
    assert "warnings" in message
    argv = mock_popen.call_args.args[0]
    assert argv[0] == "/opt/jadx/bin/jadx"
    assert argv[1:3] == ["-d", str(project_root)]
    assert "--show-bad-code" in argv
    assert argv[-1] == "/tmp/fake.apk"


def test_run_decompile_raises_on_empty_output(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project_root = jadx_manager.PROJECTS_DIR / "com.example.app"
    with patch("adb.jadx_manager.java_status", return_value={"installed": True, "path": "/bin/java", "message": None}), \
         patch("adb.jadx_manager.ensure_jadx", return_value=Path("/opt/jadx/bin/jadx")), \
         patch("adb.jadx_manager.subprocess.Popen", return_value=_FakeProcess(["error: boom\n"], returncode=1)):
        with pytest.raises(jadx_manager.JadxError, match="boom"):
            jadx_manager._run_decompile(
                Path("/tmp/fake.apk"), project_root, None, no_res=False, deobf=False, show_bad_code=True,
            )


def test_run_decompile_raises_jadx_error_when_java_missing(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project_root = jadx_manager.PROJECTS_DIR / "com.example.app"
    with patch("adb.jadx_manager.java_status", return_value={"installed": False, "message": "Java Runtime required"}):
        with pytest.raises(jadx_manager.JadxError, match="Java Runtime required"):
            jadx_manager._run_decompile(
                Path("/tmp/fake.apk"), project_root, None, no_res=False, deobf=False, show_bad_code=True,
            )


def test_run_decompile_cancellation_raises_job_cancelled(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project_root = jadx_manager.PROJECTS_DIR / "com.example.app"
    job_id = jobs.create_job("jadx_decompile", label="test")
    jobs.cancel_job(job_id)

    with patch("adb.jadx_manager.java_status", return_value={"installed": True, "path": "/bin/java", "message": None}), \
         patch("adb.jadx_manager.ensure_jadx", return_value=Path("/opt/jadx/bin/jadx")), \
         patch("adb.jadx_manager.subprocess.Popen", return_value=_FakeProcess(["a\n", "b\n"])):
        with pytest.raises(jobs.JobCancelled):
            jadx_manager._run_decompile(
                Path("/tmp/fake.apk"), project_root, job_id, no_res=False, deobf=False, show_bad_code=True,
            )


def test_run_decompile_timeout_raises_jadx_error(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project_root = jadx_manager.PROJECTS_DIR / "com.example.app"

    def infinite_lines():
        while True:
            yield "still going\n"

    proc = _FakeProcess(infinite_lines())
    times = iter([0, 0, 1000, 1000, 1000])
    with patch("adb.jadx_manager.java_status", return_value={"installed": True, "path": "/bin/java", "message": None}), \
         patch("adb.jadx_manager.ensure_jadx", return_value=Path("/opt/jadx/bin/jadx")), \
         patch("adb.jadx_manager.subprocess.Popen", return_value=proc), \
         patch("adb.jadx_manager.time.time", side_effect=lambda: next(times)), \
         patch("adb.jadx_manager.config.load_settings", return_value={"jadx_decompile_timeout_sec": 1}):
        with pytest.raises(jadx_manager.JadxError, match="timed out"):
            jadx_manager._run_decompile(
                Path("/tmp/fake.apk"), project_root, None, no_res=False, deobf=False, show_bad_code=True,
            )
    assert proc.terminated is True


# --- device-pull decompile ---------------------------------------------------

def test_decompile_pulls_apk_and_writes_meta(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    pulled_apk = tmp_path / "pulled.apk"
    pulled_apk.write_bytes(b"pulled-bytes")
    project_root = jadx_manager.project_dir("com.example.app")

    def fake_run_decompile(_apk, root, _job_id, **_kw):
        root.mkdir(parents=True, exist_ok=True)
        (root / "A.java").write_text("class A {}", encoding="utf-8")
        return "Decompiled successfully"

    with patch("adb.jadx_manager.java_status", return_value={"installed": True, "message": None}), \
         patch("adb.jadx_manager.ensure_jadx", return_value=Path("/opt/jadx/bin/jadx")), \
         patch("adb.jadx_manager.packages.validate_package", return_value="com.example.app"), \
         patch("adb.jadx_manager.packages.pull_apk", return_value=pulled_apk) as mock_pull, \
         patch("adb.jadx_manager._run_decompile", side_effect=fake_run_decompile):
        result = jadx_manager.decompile("s1", "com.example.app")

    assert result == project_root
    mock_pull.assert_called_once_with("s1", "com.example.app", jadx_manager.SOURCES_DIR / "com.example.app")
    meta = jadx_manager._project_meta(project_root)
    assert meta["source"] == "device"
    assert meta["sha256"]


def test_decompile_raises_when_java_missing(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    with patch("adb.jadx_manager.java_status", return_value={"installed": False, "message": "Java Runtime required"}), \
         patch("adb.jadx_manager.packages.validate_package", return_value="com.example.app"):
        with pytest.raises(jadx_manager.JadxError, match="Java Runtime required"):
            jadx_manager.decompile("s1", "com.example.app")


# --- listing / browsing / deleting -------------------------------------------

def test_list_projects_returns_metadata(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project_root = jadx_manager.PROJECTS_DIR / "com.example.app"
    project_root.mkdir(parents=True)
    (project_root / "A.java").write_text("class A {}", encoding="utf-8")
    jadx_manager._write_project_meta(project_root, package="com.example.app", sha256="abc123", source="upload")

    result = jadx_manager.list_projects()
    assert len(result) == 1
    assert result[0]["project"] == "com.example.app"
    assert result[0]["package"] == "com.example.app"
    assert result[0]["sha256"] == "abc123"
    assert result[0]["source"] == "upload"
    assert result[0]["size"] > 0


def test_list_projects_empty_when_no_projects(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    assert jadx_manager.list_projects() == []


def test_browse_project_lists_entries_and_breadcrumbs(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project_root = jadx_manager.PROJECTS_DIR / "com.example.app"
    (project_root / "sources").mkdir(parents=True)
    (project_root / "sources" / "A.java").write_text("class A {}", encoding="utf-8")

    root_listing = jadx_manager.browse_project("com.example.app")
    assert root_listing["ok"] is True
    assert {"name": "sources", "type": "dir"}.items() <= next(
        e for e in root_listing["entries"] if e["name"] == "sources"
    ).items()

    nested = jadx_manager.browse_project("com.example.app", "sources")
    assert nested["path"] == "sources"
    assert nested["breadcrumbs"][-1] == {"name": "sources", "path": "sources"}
    assert any(e["name"] == "A.java" and e["type"] == "file" for e in nested["entries"])


def test_browse_project_raises_when_path_missing(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    (jadx_manager.PROJECTS_DIR / "com.example.app").mkdir(parents=True)
    with pytest.raises(jadx_manager.JadxError, match="project path not found"):
        jadx_manager.browse_project("com.example.app", "missing-dir")


def test_delete_project_removes_directory_findings_and_reports(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project_root = jadx_manager.PROJECTS_DIR / "com.example.app"
    project_root.mkdir(parents=True)
    (project_root / "A.java").write_text("class A {}", encoding="utf-8")
    jadx_manager.FINDINGS_DIR.mkdir(parents=True)
    (jadx_manager.FINDINGS_DIR / "com.example.app.json").write_text("[]", encoding="utf-8")
    reports_dir = jadx_manager.REPORTS_DIR / "com.example.app"
    reports_dir.mkdir(parents=True)
    (reports_dir / "report.json").write_text("{}", encoding="utf-8")

    result = jadx_manager.delete_project("com.example.app")
    assert result == {"ok": True}
    assert not project_root.exists()
    assert not (jadx_manager.FINDINGS_DIR / "com.example.app.json").exists()
    assert not reports_dir.exists()


def test_delete_project_raises_when_missing(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    with pytest.raises(jadx_manager.JadxError, match="project not found"):
        jadx_manager.delete_project("does-not-exist")


# --- upload path ------------------------------------------------------------

class _FakeFileStorage:
    def __init__(self, filename, content=b"fake-jar-bytes"):
        self.filename = filename
        self._content = content

    def save(self, path):
        Path(path).write_bytes(self._content)


def test_save_uploaded_artifact_rejects_disallowed_extension(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    with pytest.raises(jadx_manager.JadxError):
        jadx_manager.save_uploaded_artifact(_FakeFileStorage("payload.exe"))


def test_save_uploaded_artifact_generates_project_name_when_none_given(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project, apk_path = jadx_manager.save_uploaded_artifact(_FakeFileStorage("sample.apk"))
    assert project.startswith("upload-")
    assert apk_path.is_file()
    assert apk_path.name == "sample.apk"


def test_decompile_uploaded_writes_meta_with_source_upload(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    apk_path = tmp_path / "sample.apk"
    apk_path.write_bytes(b"fake-bytes")
    project_root = jadx_manager.project_dir("my-project")

    def fake_run_decompile(_apk, root, _job_id, **_kw):
        root.mkdir(parents=True, exist_ok=True)
        (root / "A.java").write_text("class A {}", encoding="utf-8")
        return "Decompiled successfully"

    with patch("adb.jadx_manager.java_status", return_value={"installed": True, "message": None}), \
         patch("adb.jadx_manager.ensure_jadx", return_value=Path("/opt/jadx/bin/jadx")), \
         patch("adb.jadx_manager._run_decompile", side_effect=fake_run_decompile):
        jadx_manager.decompile_uploaded("my-project", apk_path)

    meta = jadx_manager._project_meta(project_root)
    assert meta["source"] == "upload"
    assert meta["package"] == "my-project"
    assert meta["sha256"]


# --- search_project --------------------------------------------------------

def test_search_project_literal_case_insensitive_and_max_results(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project = jadx_manager.PROJECTS_DIR / "com.example.app"
    project.mkdir(parents=True)
    (project / "A.java").write_text("\n".join(f"line {i} NEEDLE" for i in range(10)), encoding="utf-8")
    (project / "B.bin").write_bytes(b"\x00\x01NEEDLE\x02")  # not a recognized text extension -> skipped

    results = jadx_manager.search_project("com.example.app", "needle", max_results=3)
    assert len(results) == 3
    assert all("NEEDLE" in r["snippet"] for r in results)
    assert all(r["path"] == "A.java" for r in results)


def test_search_project_regex_mode(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project = jadx_manager.PROJECTS_DIR / "com.example.app"
    project.mkdir(parents=True)
    (project / "A.java").write_text("String url = \"https://example.com/x\";", encoding="utf-8")

    results = jadx_manager.search_project("com.example.app", r"https?://\S+", regex=True)
    assert len(results) == 1
    assert "example.com" in results[0]["snippet"]


def test_search_project_rejects_invalid_regex(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    (jadx_manager.PROJECTS_DIR / "com.example.app").mkdir(parents=True)
    with pytest.raises(jadx_manager.JadxError, match="invalid regex"):
        jadx_manager.search_project("com.example.app", "(unclosed", regex=True)


# --- manifest_summary --------------------------------------------------------

def test_manifest_summary_parses_permissions_components_and_flags(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project_root = jadx_manager.PROJECTS_DIR / "com.example.app"
    _write_manifest(project_root)

    summary = jadx_manager.manifest_summary("com.example.app")
    assert summary["package"] == "com.example.app"
    assert summary["min_sdk"] == "21"
    assert summary["target_sdk"] == "34"
    assert summary["debuggable"] == "true"
    assert summary["allow_backup"] == "true"
    assert summary["permissions"] == ["android.permission.CAMERA"]
    assert summary["activities"][0]["exported"] == "true"
    assert summary["activities"][0]["intent_actions"] == ["android.intent.action.MAIN"]


def test_manifest_summary_missing_manifest_raises_clear_error(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    (jadx_manager.PROJECTS_DIR / "com.example.app").mkdir(parents=True)
    with pytest.raises(jadx_manager.JadxError, match="AndroidManifest.xml not found"):
        jadx_manager.manifest_summary("com.example.app")


# --- static findings ---------------------------------------------------------

def test_run_static_checks_flags_manifest_and_source_issues(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project_root = jadx_manager.PROJECTS_DIR / "com.example.app"
    _write_manifest(project_root)
    (project_root / "Crypto.java").write_text(
        'Cipher c = Cipher.getInstance("DES/ECB/PKCS5Padding");\n'
        'String url = "https://api.example.com/leak";\n',
        encoding="utf-8",
    )

    findings = jadx_manager.run_static_checks("com.example.app")
    ids = {f["id"] for f in findings}
    assert "exported-activity-no-permission" in ids
    assert "debuggable-true" in ids
    assert "allow-backup-true" in ids
    assert "risky-permission" in ids
    assert "weak-crypto-des" in ids
    assert "weak-crypto-ecb" in ids
    assert "hardcoded-url" in ids

    # Persisted to disk and reloadable.
    reloaded = jadx_manager.get_findings("com.example.app")
    assert reloaded == findings


def test_get_findings_returns_none_when_never_run(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    assert jadx_manager.get_findings("never-run") is None


# --- report export -----------------------------------------------------------

def test_export_report_json_and_markdown_round_trip(tmp_path, monkeypatch):
    _set_dirs(monkeypatch, tmp_path)
    project_root = jadx_manager.PROJECTS_DIR / "com.example.app"
    _write_manifest(project_root)
    jadx_manager._write_project_meta(project_root, package="com.example.app", sha256="deadbeef", source="device")

    with patch("adb.jadx_manager.get_status", return_value={
        "jadx": {"version": "1.5.1", "pinned_version": "1.5.1"},
        "java": {"version": "openjdk 17"},
    }):
        json_path = jadx_manager.export_report("com.example.app", fmt="json")
        md_path = jadx_manager.export_report("com.example.app", fmt="md")

    import json
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    assert doc["sha256"] == "deadbeef"
    assert doc["tool_versions"]["jadx"] == "1.5.1"
    assert "Authorized analysis only" in doc["authorized_use_statement"]

    md_text = md_path.read_text(encoding="utf-8")
    assert "deadbeef" in md_text
    assert "Authorized analysis only" in md_text
