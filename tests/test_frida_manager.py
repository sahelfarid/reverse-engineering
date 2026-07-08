import lzma
import sys
import types
from unittest.mock import MagicMock, patch

import pytest
import requests

import config
from adb import frida_manager
from adb import manager


def test_resolve_frida_server_url_maps_supported_abis():
    base = "https://github.com/frida/frida/releases/download/16.2.1"
    assert frida_manager.resolve_frida_server_url("16.2.1", "armeabi-v7a") == (
        f"{base}/frida-server-16.2.1-android-arm.xz"
    )
    assert frida_manager.resolve_frida_server_url("16.2.1", "arm64-v8a") == (
        f"{base}/frida-server-16.2.1-android-arm64.xz"
    )
    assert frida_manager.resolve_frida_server_url("16.2.1", "x86") == (
        f"{base}/frida-server-16.2.1-android-x86.xz"
    )
    assert frida_manager.resolve_frida_server_url("16.2.1", "x86_64") == (
        f"{base}/frida-server-16.2.1-android-x86_64.xz"
    )


def test_resolve_frida_server_url_rejects_unknown_abi():
    with pytest.raises(manager.AdbError):
        frida_manager.resolve_frida_server_url("16.2.1", "mips")


def test_script_store_crud_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)

    result = frida_manager.save_script("demo", "console.log('ok');")
    assert result == {"ok": True, "name": "demo"}
    scripts = frida_manager.list_scripts()
    assert scripts["demo"]["source"] == "console.log('ok');"
    assert scripts["demo"]["readonly"] is False

    with pytest.raises(manager.AdbError):
        frida_manager.save_script("../escape", "bad")
    with pytest.raises(manager.AdbError):
        frida_manager.delete_script("..\\escape")

    assert frida_manager.delete_script("demo") == {"ok": True}
    assert "demo" not in frida_manager.list_scripts()


def test_default_scripts_are_readonly(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    default_name = next(iter(frida_manager.DEFAULT_SCRIPTS))
    with pytest.raises(manager.AdbError):
        frida_manager.save_script(default_name, "console.log('replace');")
    with pytest.raises(manager.AdbError):
        frida_manager.delete_script(default_name)


def test_attach_detach_session_registry_with_mocked_frida(monkeypatch):
    frida_manager._sessions.clear()

    class FakeScript:
        def __init__(self):
            self.handlers = {}
            self.loaded = False
            self.unloaded = False

        def on(self, event, handler):
            self.handlers[event] = handler

        def load(self):
            self.loaded = True
            self.handlers["message"]({"type": "send", "payload": "ready"}, None)

        def unload(self):
            self.unloaded = True

    class FakeSession:
        def __init__(self):
            self.script = FakeScript()
            self.detached = False

        def create_script(self, source):
            assert "console.log" in source
            return self.script

        def detach(self):
            self.detached = True

    class FakeDevice:
        id = "serial-1"

        def __init__(self):
            self.session = FakeSession()
            self.attached_to = None

        def attach(self, target):
            self.attached_to = target
            return self.session

    fake_device = FakeDevice()
    fake_frida = types.SimpleNamespace(
        __version__="16.2.1",
        get_device_manager=lambda: types.SimpleNamespace(enumerate_devices=lambda: [fake_device]),
        get_usb_device=lambda timeout=5: fake_device,
    )
    monkeypatch.setitem(sys.modules, "frida", fake_frida)
    monkeypatch.setattr(frida_manager, "check_version_compatibility", lambda serial: None)

    session_id = frida_manager.attach("serial-1", "1234", "console.log('hi');")

    assert fake_device.attached_to == 1234
    assert session_id in frida_manager._sessions
    entry = frida_manager._sessions[session_id]
    assert entry["script"].loaded is True
    assert entry["queue"].get_nowait()["message"]["payload"] == "ready"

    assert frida_manager.detach(session_id) == {"ok": True, "detached": True}
    assert session_id not in frida_manager._sessions
    assert fake_device.session.script.unloaded is True
    assert fake_device.session.detached is True


def _fake_streaming_response(body: bytes):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.iter_content = MagicMock(return_value=[body])
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_ensure_frida_server_downloads_decompresses_and_cleans_up(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VENDOR_DIR", tmp_path)
    compressed = lzma.compress(b"binary-content")
    with patch("adb.frida_manager._frida_version", return_value="16.2.1"), \
         patch("adb.frida_manager.devices.get_basic_properties", return_value={"abi": "arm64-v8a"}), \
         patch("adb.frida_manager.requests.get", return_value=_fake_streaming_response(compressed)):
        path = frida_manager.ensure_frida_server("s1")
    assert path.read_bytes() == b"binary-content"
    assert not path.with_suffix(".xz").exists()


def test_ensure_frida_server_returns_cached_without_downloading(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VENDOR_DIR", tmp_path)
    dest = tmp_path / "frida" / "16.2.1" / "arm64" / "frida-server"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"already-cached")
    with patch("adb.frida_manager._frida_version", return_value="16.2.1"), \
         patch("adb.frida_manager.devices.get_basic_properties", return_value={"abi": "arm64-v8a"}), \
         patch("adb.frida_manager.requests.get") as mock_get:
        path = frida_manager.ensure_frida_server("s1")
    assert path == dest
    mock_get.assert_not_called()


def test_ensure_frida_server_raises_when_frida_package_missing():
    with patch("adb.frida_manager._frida_version", return_value=None):
        with pytest.raises(manager.AdbError, match="frida package not installed"):
            frida_manager.ensure_frida_server("s1")


def test_ensure_frida_server_raises_and_cleans_up_on_download_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VENDOR_DIR", tmp_path)
    with patch("adb.frida_manager._frida_version", return_value="16.2.1"), \
         patch("adb.frida_manager.devices.get_basic_properties", return_value={"abi": "arm64-v8a"}), \
         patch("adb.frida_manager.requests.get", side_effect=requests.RequestException("network down")):
        with pytest.raises(manager.AdbError, match="Failed to download frida-server"):
            frida_manager.ensure_frida_server("s1")
    compressed_path = tmp_path / "frida" / "16.2.1" / "arm64" / "frida-server.xz"
    assert not compressed_path.exists()


def test_push_server_requires_root():
    with patch("adb.frida_manager.manager.has_root_shell", return_value=False):
        with pytest.raises(manager.AdbError, match="rooted"):
            frida_manager.push_server("s1")


def test_push_server_success(tmp_path):
    local_server = tmp_path / "frida-server"
    local_server.write_bytes(b"binary")
    with patch("adb.frida_manager.manager.has_root_shell", return_value=True), \
         patch("adb.frida_manager.ensure_frida_server", return_value=local_server), \
         patch("adb.frida_manager.manager.run", return_value=MagicMock(returncode=0, stderr="")), \
         patch("adb.frida_manager.manager.shell", return_value=("", "", 0)) as mock_shell:
        result = frida_manager.push_server("s1")
    assert result == {"ok": True, "remote_path": frida_manager.FRIDA_SERVER_REMOTE}
    assert "chmod 755" in mock_shell.call_args[0][1]


def test_push_server_raises_on_push_failure(tmp_path):
    local_server = tmp_path / "frida-server"
    local_server.write_bytes(b"binary")
    with patch("adb.frida_manager.manager.has_root_shell", return_value=True), \
         patch("adb.frida_manager.ensure_frida_server", return_value=local_server), \
         patch("adb.frida_manager.manager.run", return_value=MagicMock(returncode=1, stderr="push failed")):
        with pytest.raises(manager.AdbError, match="push failed"):
            frida_manager.push_server("s1")


def test_start_server_pushes_if_needed_and_starts():
    frida_manager._server_pids.clear()
    with patch("adb.frida_manager.manager.has_root_shell", return_value=True), \
         patch("adb.frida_manager._is_pushed", return_value=False), \
         patch("adb.frida_manager.push_server", return_value={"ok": True}) as mock_push, \
         patch("adb.frida_manager._running_pid", side_effect=[None, "4321"]), \
         patch("adb.frida_manager.manager.shell", return_value=("", "", 0)), \
         patch("adb.frida_manager.time.sleep"):
        result = frida_manager.start_server("s1")
    assert result == {"ok": True, "pid": "4321"}
    mock_push.assert_called_once_with("s1")
    assert frida_manager._server_pids["s1"] == "4321"


def test_start_server_already_running_short_circuits():
    with patch("adb.frida_manager.manager.has_root_shell", return_value=True), \
         patch("adb.frida_manager._is_pushed", return_value=True), \
         patch("adb.frida_manager._running_pid", return_value="999"):
        result = frida_manager.start_server("s1")
    assert result == {"ok": True, "pid": "999", "already_running": True}


def test_start_server_raises_when_start_command_fails():
    with patch("adb.frida_manager.manager.has_root_shell", return_value=True), \
         patch("adb.frida_manager._is_pushed", return_value=True), \
         patch("adb.frida_manager._running_pid", return_value=None), \
         patch("adb.frida_manager.manager.shell", return_value=("", "permission denied", 1)):
        with pytest.raises(manager.AdbError, match="permission denied"):
            frida_manager.start_server("s1")


def test_start_server_raises_when_no_pid_reported():
    with patch("adb.frida_manager.manager.has_root_shell", return_value=True), \
         patch("adb.frida_manager._is_pushed", return_value=True), \
         patch("adb.frida_manager._running_pid", return_value=None), \
         patch("adb.frida_manager.manager.shell", return_value=("", "", 0)), \
         patch("adb.frida_manager.time.sleep"):
        with pytest.raises(manager.AdbError, match="did not report a running pid"):
            frida_manager.start_server("s1")


def test_push_and_start_server_composes_both():
    with patch("adb.frida_manager.push_server", return_value={"ok": True, "remote_path": "x"}) as mock_push, \
         patch("adb.frida_manager.start_server", return_value={"ok": True, "pid": "123"}) as mock_start:
        result = frida_manager.push_and_start_server("s1")
    assert result == {"ok": True, "push": {"ok": True, "remote_path": "x"}, "pid": "123"}
    mock_push.assert_called_once_with("s1")
    mock_start.assert_called_once_with("s1")


def test_stop_server_not_running():
    with patch("adb.frida_manager._running_pid", return_value=None):
        assert frida_manager.stop_server("s1") == {"ok": True, "stopped": False}


def test_stop_server_success():
    frida_manager._server_pids["s1"] = "555"
    with patch("adb.frida_manager._running_pid", return_value="555"), \
         patch("adb.frida_manager.manager.shell", return_value=("", "", 0)) as mock_shell:
        result = frida_manager.stop_server("s1")
    assert result == {"ok": True, "stopped": True, "pid": "555"}
    assert "s1" not in frida_manager._server_pids
    assert mock_shell.call_count == 2  # kill, then rm pid file


def test_stop_server_raises_on_kill_failure_using_stderr():
    with patch("adb.frida_manager._running_pid", return_value="555"), \
         patch("adb.frida_manager.manager.shell", return_value=("", "operation not permitted", 1)):
        with pytest.raises(manager.AdbError, match="operation not permitted"):
            frida_manager.stop_server("s1")


def test_stop_server_raises_generic_message_when_stderr_empty():
    with patch("adb.frida_manager._running_pid", return_value="555"), \
         patch("adb.frida_manager.manager.shell", return_value=("", "", 1)):
        with pytest.raises(manager.AdbError, match="failed to stop pid 555"):
            frida_manager.stop_server("s1")


def test_get_status_aggregates_devices():
    with patch("adb.frida_manager._frida_version", return_value="16.2.1"), \
         patch("adb.frida_manager.devices.list_devices", return_value=[
             {"serial": "s1", "state": "device"}, {"serial": "s2", "state": "unauthorized"},
         ]), \
         patch("adb.frida_manager.devices.get_basic_properties", return_value={"abi": "arm64-v8a"}), \
         patch("adb.frida_manager._server_path") as mock_server_path, \
         patch("adb.frida_manager.manager.has_root_shell", return_value=True), \
         patch("adb.frida_manager._is_pushed", return_value=True), \
         patch("adb.frida_manager.get_server_version", return_value="16.2.1"), \
         patch("adb.frida_manager._running_pid", return_value="123"):
        mock_server_path.return_value.is_file.return_value = True
        result = frida_manager.get_status()
    assert result["python_installed"] is True
    assert len(result["devices"]) == 1  # unauthorized device excluded
    assert result["devices"][0]["serial"] == "s1"
    assert result["devices"][0]["server_running"] is True
    assert result["devices"][0]["server_version"] == "16.2.1"
    assert result["devices"][0]["version_match"] is True


def test_get_status_handles_list_devices_failure():
    with patch("adb.frida_manager._frida_version", return_value=None), \
         patch("adb.frida_manager.devices.list_devices", side_effect=manager.AdbError("no adb")):
        result = frida_manager.get_status()
    assert result["python_installed"] is False
    assert result["devices"] == []


def test_get_status_captures_per_device_errors():
    with patch("adb.frida_manager._frida_version", return_value="16.2.1"), \
         patch("adb.frida_manager.devices.list_devices", return_value=[{"serial": "s1", "state": "device"}]), \
         patch("adb.frida_manager.devices.get_basic_properties", side_effect=manager.AdbError("device offline")):
        result = frida_manager.get_status()
    assert result["devices"] == [{"serial": "s1", "error": "device offline"}]


def test_list_processes_uses_frida_device_when_available(monkeypatch):
    class FakeProcess:
        def __init__(self, pid, name):
            self.pid = pid
            self.name = name

    fake_device = types.SimpleNamespace(
        enumerate_processes=lambda: [FakeProcess(2, "zeta"), FakeProcess(1, "alpha")]
    )
    with patch("adb.frida_manager._frida_device", return_value=fake_device):
        result = frida_manager.list_processes("s1")
    assert [p["name"] for p in result] == ["alpha", "zeta"]


def test_list_processes_falls_back_to_adb_on_frida_failure():
    with patch("adb.frida_manager._frida_device", side_effect=RuntimeError("no usb device")), \
         patch("adb.frida_manager.process_manager.list_processes", return_value={"processes": [{"pid": 1, "name": "init"}]}):
        result = frida_manager.list_processes("s1")
    assert result == [{"pid": 1, "name": "init"}]


def test_list_applications_sorts_running_first_then_name():
    apps = [
        types.SimpleNamespace(identifier="com.z.bg", name="Zeta", pid=0),
        types.SimpleNamespace(identifier="com.a.run", name="Alpha", pid=1234),
        types.SimpleNamespace(identifier="com.b.bg", name="Beta", pid=0),
    ]
    fake_device = types.SimpleNamespace(enumerate_applications=lambda: apps)
    with patch("adb.frida_manager._frida_device", return_value=fake_device):
        result = frida_manager.list_applications("s1")
    assert [a["name"] for a in result] == ["Alpha", "Beta", "Zeta"]
    assert result[0] == {"identifier": "com.a.run", "name": "Alpha", "pid": 1234, "running": True}
    assert result[1]["running"] is False and result[1]["pid"] is None


def test_list_applications_raises_adb_error_on_frida_failure():
    fake_device = types.SimpleNamespace(
        enumerate_applications=MagicMock(side_effect=RuntimeError("server not running"))
    )
    with patch("adb.frida_manager._frida_device", return_value=fake_device):
        with pytest.raises(manager.AdbError, match="failed to enumerate applications"):
            frida_manager.list_applications("s1")


def test_get_frontmost_application_returns_public_shape():
    app = types.SimpleNamespace(identifier="com.a.run", name="Alpha", pid=42)
    fake_device = types.SimpleNamespace(get_frontmost_application=lambda: app)
    with patch("adb.frida_manager._frida_device", return_value=fake_device):
        result = frida_manager.get_frontmost_application("s1")
    assert result == {"identifier": "com.a.run", "name": "Alpha", "pid": 42, "running": True}


def test_get_frontmost_application_returns_none_when_nothing_foreground():
    fake_device = types.SimpleNamespace(get_frontmost_application=lambda: None)
    with patch("adb.frida_manager._frida_device", return_value=fake_device):
        assert frida_manager.get_frontmost_application("s1") is None


def test_stream_messages_raises_for_unknown_session():
    with pytest.raises(manager.AdbError, match="session not found"):
        next(frida_manager.stream_messages("does-not-exist"))


def test_stream_messages_yields_queued_message_then_heartbeat():
    import queue as queue_module

    class _FakeQueue:
        """Avoids real blocking on the hardcoded 15s get(timeout=...) in
        stream_messages() -- raises Empty immediately once drained."""
        def __init__(self, items):
            self._items = list(items)

        def get(self, timeout=None):
            if self._items:
                return self._items.pop(0)
            raise queue_module.Empty()

    frida_manager._sessions.clear()
    fake_queue = _FakeQueue([{"message": {"type": "send", "payload": "hi"}}])
    frida_manager._sessions["sess1"] = {"queue": fake_queue}
    gen = frida_manager.stream_messages("sess1")
    first = next(gen)
    assert first["message"]["payload"] == "hi"
    second = next(gen)
    assert second["message"]["type"] == "heartbeat"
    gen.close()
    frida_manager._sessions.clear()


def test_drain_messages_raises_for_unknown_session():
    with pytest.raises(manager.AdbError, match="session not found"):
        frida_manager.drain_messages("does-not-exist", 1.0)


def test_drain_messages_collects_until_queue_empty():
    import queue as queue_module

    class _FakeQueue:
        """Same rationale as the stream_messages fake above: raises Empty
        immediately once drained instead of blocking for the real timeout."""
        def __init__(self, items):
            self._items = list(items)

        def get(self, timeout=None):
            if self._items:
                return self._items.pop(0)
            raise queue_module.Empty()

    frida_manager._sessions.clear()
    fake_queue = _FakeQueue([{"message": {"type": "send", "payload": "a"}}, {"message": {"type": "send", "payload": "b"}}])
    frida_manager._sessions["sess1"] = {"queue": fake_queue}
    result = frida_manager.drain_messages("sess1", 5.0)
    assert [m["message"]["payload"] for m in result] == ["a", "b"]
    frida_manager._sessions.clear()


def test_drain_messages_returns_empty_when_deadline_already_passed():
    frida_manager._sessions.clear()
    frida_manager._sessions["sess1"] = {"queue": object()}  # never touched: deadline is already past
    result = frida_manager.drain_messages("sess1", -1.0)
    assert result == []
    frida_manager._sessions.clear()


def test_versions_compatible_matches_major_minor():
    assert frida_manager.versions_compatible("16.2.1", "16.2.5") is True
    assert frida_manager.versions_compatible("16.2.1", "16.2.1") is True


def test_versions_compatible_rejects_major_minor_divergence():
    assert frida_manager.versions_compatible("16.2.1", "16.3.0") is False
    assert frida_manager.versions_compatible("17.0.0", "16.2.1") is False


def test_versions_compatible_is_permissive_when_side_unknown():
    assert frida_manager.versions_compatible(None, "16.2.1") is True
    assert frida_manager.versions_compatible("16.2.1", None) is True
    assert frida_manager.versions_compatible("16.2.1", "garbage") is True


def test_get_server_version_returns_none_when_not_pushed():
    with patch("adb.frida_manager._is_pushed", return_value=False):
        assert frida_manager.get_server_version("s1") is None


def test_get_server_version_parses_reported_version():
    with patch("adb.frida_manager._is_pushed", return_value=True), \
         patch("adb.frida_manager.manager.shell", return_value=("16.2.1\n", "", 0)):
        assert frida_manager.get_server_version("s1") == "16.2.1"


def test_get_server_version_returns_none_on_shell_failure():
    with patch("adb.frida_manager._is_pushed", return_value=True), \
         patch("adb.frida_manager.manager.shell", return_value=("", "not found", 1)):
        assert frida_manager.get_server_version("s1") is None


def test_check_version_compatibility_raises_on_mismatch():
    with patch("adb.frida_manager._frida_version", return_value="17.0.0"), \
         patch("adb.frida_manager.get_server_version", return_value="16.2.1"):
        with pytest.raises(manager.AdbError, match="version mismatch"):
            frida_manager.check_version_compatibility("s1")


def test_check_version_compatibility_passes_when_compatible():
    with patch("adb.frida_manager._frida_version", return_value="16.2.9"), \
         patch("adb.frida_manager.get_server_version", return_value="16.2.1"):
        assert frida_manager.check_version_compatibility("s1") is None


def test_script_hash_is_stable_sha256():
    h1 = frida_manager.script_hash("console.log(1);")
    h2 = frida_manager.script_hash("console.log(1);")
    h3 = frida_manager.script_hash("console.log(2);")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64
