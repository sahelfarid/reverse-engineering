import io
import os
import stat
import zipfile
from unittest.mock import MagicMock, patch

import pytest
import requests

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


def _fake_streaming_response(body: bytes):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.iter_content = MagicMock(return_value=[body])
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_download_platform_tools_writes_response_body(tmp_path):
    dest = tmp_path / "platform-tools.zip"
    fake_resp = _fake_streaming_response(b"zip-bytes")
    with patch("adb.manager.requests.get", return_value=fake_resp) as mock_get:
        result = manager.download_platform_tools(dest)
    assert result == dest
    assert dest.read_bytes() == b"zip-bytes"
    assert mock_get.call_args.kwargs["stream"] is True


def test_download_platform_tools_raises_on_network_failure(tmp_path):
    dest = tmp_path / "platform-tools.zip"
    with patch("adb.manager.requests.get", side_effect=requests.RequestException("boom")):
        with pytest.raises(manager.AdbInstallError):
            manager.download_platform_tools(dest)


def test_safe_extract_rejects_zip_slip_member(tmp_path):
    dest = tmp_path / "vendor"
    dest.mkdir()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.txt", "pwned")
    buf.seek(0)
    with zipfile.ZipFile(buf) as zf:
        with pytest.raises(manager.AdbInstallError):
            manager._safe_extract(zf, dest)
    assert not (tmp_path / "evil.txt").exists()


def test_safe_extract_allows_normal_members(tmp_path):
    dest = tmp_path / "vendor"
    dest.mkdir()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("platform-tools/adb", "fake-binary")
    buf.seek(0)
    with zipfile.ZipFile(buf) as zf:
        manager._safe_extract(zf, dest)
    assert (dest / "platform-tools" / "adb").read_text() == "fake-binary"


def test_install_adb_raises_on_bad_zip(tmp_path, monkeypatch):
    zip_path = tmp_path / "platform-tools.zip"
    monkeypatch.setattr(manager.config, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(manager.config, "VENDOR_DIR", tmp_path / "vendor")
    monkeypatch.setattr(manager, "download_platform_tools", lambda dest: zip_path.write_bytes(b"not a zip") or dest)
    with pytest.raises(manager.AdbInstallError):
        manager.install_adb()
    assert not zip_path.exists()  # cleaned up even on failure


def test_install_adb_raises_when_executable_missing_after_extract(tmp_path, monkeypatch):
    zip_path = tmp_path / "platform-tools.zip"
    vendor_dir = tmp_path / "vendor"

    def fake_download(dest):
        with zipfile.ZipFile(dest, "w") as zf:
            zf.writestr("platform-tools/readme.txt", "no adb here")
        return dest

    monkeypatch.setattr(manager.config, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(manager.config, "VENDOR_DIR", vendor_dir)
    monkeypatch.setattr(manager, "download_platform_tools", fake_download)
    with pytest.raises(manager.AdbInstallError, match="not found after extraction"):
        manager.install_adb()
    assert not zip_path.exists()


@pytest.mark.skipif(os.name == "nt", reason="chmod executable bit is POSIX-only")
def test_install_adb_sets_executable_bit_on_posix(tmp_path, monkeypatch):
    zip_path = tmp_path / "platform-tools.zip"
    vendor_dir = tmp_path / "vendor"

    def fake_download(dest):
        with zipfile.ZipFile(dest, "w") as zf:
            zf.writestr("platform-tools/adb", "fake-binary")
        return dest

    monkeypatch.setattr(manager.config, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(manager.config, "VENDOR_DIR", vendor_dir)
    monkeypatch.setattr(manager, "download_platform_tools", fake_download)
    monkeypatch.setattr(manager, "get_adb_status", lambda: {"installed": True, "source": "vendor", "version": "1.0", "path": str(vendor_dir / "platform-tools" / "adb")})

    manager.install_adb()

    mode = (vendor_dir / "platform-tools" / "adb").stat().st_mode
    assert mode & stat.S_IXUSR
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH


def test_run_maps_timeout_to_adb_error(monkeypatch):
    monkeypatch.setattr(manager, "find_adb", lambda: manager.Path("/usr/bin/adb"))
    with patch("adb.manager.subprocess.run", side_effect=manager.subprocess.TimeoutExpired(cmd="adb", timeout=5)):
        with pytest.raises(manager.AdbError):
            manager.run(["devices"], timeout=5)


def test_run_binary_maps_timeout_to_adb_error(monkeypatch):
    monkeypatch.setattr(manager, "find_adb", lambda: manager.Path("/usr/bin/adb"))
    with patch("adb.manager.subprocess.run", side_effect=manager.subprocess.TimeoutExpired(cmd="adb", timeout=5)):
        with pytest.raises(manager.AdbError):
            manager.run_binary(["exec-out", "screencap", "-p"], timeout=5)
