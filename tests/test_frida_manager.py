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


def test_bundled_bypass_templates_present_and_readonly(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    scripts = frida_manager.list_scripts()
    for name in ("template-ssl-pinning-bypass", "template-root-detection-bypass"):
        assert name in scripts
        assert scripts[name]["readonly"] is True
        assert "Java.perform" in scripts[name]["source"]
    # SSL agent covers multiple frameworks, not a single stub
    ssl_source = scripts["template-ssl-pinning-bypass"]["source"]
    assert "okhttp3.CertificatePinner" in ssl_source
    assert "TrustManagerImpl" in ssl_source
    assert "WebViewClient" in ssl_source


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
            self.log_handler = None

        def on(self, event, handler):
            self.handlers[event] = handler

        def set_log_handler(self, handler):
            self.log_handler = handler

        def load(self):
            self.loaded = True
            self.handlers["message"]({"type": "send", "payload": "ready"}, None)
            if self.log_handler:
                self.log_handler("info", "hello from console.log")

        def unload(self):
            self.unloaded = True

    class FakeSession:
        def __init__(self):
            self.script = FakeScript()
            self.detached = False

        def create_script(self, source, name=None, snapshot=None, runtime=None):
            assert "console.log" in source
            self.last_runtime = runtime
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
    assert entry["script"].log_handler is not None
    assert entry.get("runtime") is None
    assert entry["queue"].get_nowait()["message"]["payload"] == "ready"
    log_msg = entry["queue"].get_nowait()["message"]
    assert log_msg == {"type": "log", "level": "info", "payload": "hello from console.log"}

    assert frida_manager.detach(session_id) == {"ok": True, "detached": True}
    assert session_id not in frida_manager._sessions
    assert fake_device.session.script.unloaded is True
    assert fake_device.session.detached is True


def test_attach_passes_runtime_to_create_script(monkeypatch):
    frida_manager._sessions.clear()

    class FakeScript:
        def on(self, event, handler):
            pass

        def set_log_handler(self, handler):
            pass

        def load(self):
            pass

        def unload(self):
            pass

    class FakeSession:
        def __init__(self):
            self.create_kwargs = None

        def create_script(self, source, name=None, snapshot=None, runtime=None):
            self.create_kwargs = {"runtime": runtime}
            return FakeScript()

        def on(self, event, handler):
            pass

        def detach(self):
            pass

    class FakeDevice:
        id = "serial-1"

        def __init__(self):
            self.session = FakeSession()

        def attach(self, target):
            return self.session

    fake_device = FakeDevice()
    fake_frida = types.SimpleNamespace(
        __version__="16.2.1",
        get_device_manager=lambda: types.SimpleNamespace(enumerate_devices=lambda: [fake_device]),
        get_usb_device=lambda timeout=5: fake_device,
    )
    monkeypatch.setitem(sys.modules, "frida", fake_frida)
    monkeypatch.setattr(frida_manager, "check_version_compatibility", lambda serial: None)

    session_id = frida_manager.attach("serial-1", "99", "console.log(1);", runtime="v8")
    assert fake_device.session.create_kwargs == {"runtime": "v8"}
    assert frida_manager._sessions[session_id]["runtime"] == "v8"
    frida_manager.detach(session_id)


def test_attach_rejects_invalid_runtime():
    frida_manager._sessions.clear()
    with pytest.raises(manager.AdbError, match="invalid runtime"):
        frida_manager.attach("s1", "1", "console.log(1);", runtime="spidermonkey")


def test_inject_script_params_prepends_const():
    out = frida_manager.inject_script_params("console.log(PARAMS.x);", {"x": 1, "y": "z"})
    assert out.startswith("const PARAMS = ")
    assert "console.log(PARAMS.x);" in out
    assert '"x":1' in out or '"x": 1' in out


def test_inject_script_params_noop_when_empty():
    assert frida_manager.inject_script_params("src", None) == "src"
    assert frida_manager.inject_script_params("src", {}) == "src"


def test_inject_script_params_rejects_non_dict():
    with pytest.raises(manager.AdbError, match="JSON object"):
        frida_manager.inject_script_params("src", ["a"])


def test_attach_injects_params_into_create_script(monkeypatch):
    frida_manager._sessions.clear()
    created = {}

    class FakeScript:
        def on(self, event, handler):
            pass

        def set_log_handler(self, handler):
            pass

        def load(self):
            pass

        def unload(self):
            pass

    class FakeSession:
        def create_script(self, source, name=None, snapshot=None, runtime=None):
            created["source"] = source
            return FakeScript()

        def on(self, event, handler):
            pass

        def detach(self):
            pass

        def is_detached(self):
            return False

    class FakeDevice:
        id = "serial-1"

        def __init__(self):
            self.session = FakeSession()

        def attach(self, target):
            return self.session

    fake_device = FakeDevice()
    fake_frida = types.SimpleNamespace(
        __version__="16.2.1",
        get_device_manager=lambda: types.SimpleNamespace(enumerate_devices=lambda: [fake_device]),
        get_usb_device=lambda timeout=5: fake_device,
    )
    monkeypatch.setitem(sys.modules, "frida", fake_frida)
    monkeypatch.setattr(frida_manager, "check_version_compatibility", lambda serial: None)

    sid = frida_manager.attach(
        "serial-1", "1", "console.log(PARAMS.className);",
        params={"className": "com.example.App"},
    )
    assert created["source"].startswith("const PARAMS = ")
    assert "com.example.App" in created["source"]
    assert "console.log(PARAMS.className);" in created["source"]
    frida_manager.detach(sid)


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


def test_eternalize_session_detaches_without_unload():
    frida_manager._sessions.clear()
    script = MagicMock()
    session = MagicMock()
    session.is_detached.return_value = False
    frida_manager._sessions["e1"] = {
        "detached": False, "script": script, "session": session,
    }
    assert frida_manager.eternalize_session("e1") == {"ok": True, "eternalized": True}
    script.eternalize.assert_called_once_with()
    script.unload.assert_not_called()
    session.detach.assert_called_once_with()
    assert "e1" not in frida_manager._sessions


def test_eternalize_rejects_detached_session():
    frida_manager._sessions.clear()
    frida_manager._sessions["e1"] = {"detached": True, "script": MagicMock()}
    with pytest.raises(manager.AdbError, match="detached"):
        frida_manager.eternalize_session("e1")


def test_list_script_exports_returns_sorted_names():
    frida_manager._sessions.clear()
    script = types.SimpleNamespace(list_exports=lambda: ["zzz", "aaa"])
    frida_manager._sessions["s"] = {"script": script}
    assert frida_manager.list_script_exports("s") == ["aaa", "zzz"]
    frida_manager._sessions.clear()


def test_list_script_exports_unknown_session():
    frida_manager._sessions.clear()
    with pytest.raises(manager.AdbError, match="session not found"):
        frida_manager.list_script_exports("nope")


def test_list_script_exports_rejects_detached_session():
    frida_manager._sessions.clear()
    frida_manager._sessions["s"] = {"detached": True, "script": object()}
    with pytest.raises(manager.AdbError, match="detached"):
        frida_manager.list_script_exports("s")
    frida_manager._sessions.clear()


def test_call_script_export_invokes_and_json_sanitizes_bytes():
    frida_manager._sessions.clear()
    exports = types.SimpleNamespace(get_secret=lambda a, b: {"blob": b"\x01\x02", "sum": a + b})
    script = types.SimpleNamespace(list_exports=lambda: ["get_secret"], exports=exports)
    frida_manager._sessions["s"] = {"script": script}
    result = frida_manager.call_script_export("s", "get_secret", [2, 3])
    assert result == {"blob": {"__bytes_hex__": "0102"}, "sum": 5}
    frida_manager._sessions.clear()


def test_call_script_export_rejects_invalid_name():
    frida_manager._sessions.clear()
    frida_manager._sessions["s"] = {"script": object()}
    with pytest.raises(manager.AdbError, match="invalid export name"):
        frida_manager.call_script_export("s", "bad-name", [])
    frida_manager._sessions.clear()


def test_call_script_export_rejects_non_list_args():
    frida_manager._sessions.clear()
    frida_manager._sessions["s"] = {"script": types.SimpleNamespace(list_exports=lambda: ["foo"])}
    with pytest.raises(manager.AdbError, match="must be a JSON array"):
        frida_manager.call_script_export("s", "foo", {"not": "a list"})
    frida_manager._sessions.clear()


def test_call_script_export_unknown_export():
    frida_manager._sessions.clear()
    script = types.SimpleNamespace(list_exports=lambda: ["foo"], exports=types.SimpleNamespace())
    frida_manager._sessions["s"] = {"script": script}
    with pytest.raises(manager.AdbError, match="not found"):
        frida_manager.call_script_export("s", "bar", [])
    frida_manager._sessions.clear()


def test_interrupt_script_calls_script_interrupt():
    frida_manager._sessions.clear()
    script = MagicMock()
    session = MagicMock()
    session.is_detached.return_value = False
    frida_manager._sessions["s"] = {"detached": False, "script": script, "session": session}
    assert frida_manager.interrupt_script("s") == {"ok": True, "interrupted": True}
    script.interrupt.assert_called_once_with()
    assert "s" in frida_manager._sessions  # interrupt keeps the session alive
    frida_manager._sessions.clear()


def test_terminate_script_terminates_and_drops_session():
    frida_manager._sessions.clear()
    script = MagicMock()
    session = MagicMock()
    session.is_detached.return_value = False
    frida_manager._sessions["s"] = {"detached": False, "script": script, "session": session}
    assert frida_manager.terminate_script("s") == {"ok": True, "terminated": True}
    script.terminate.assert_called_once_with()
    session.detach.assert_called_once_with()
    assert "s" not in frida_manager._sessions
    frida_manager._sessions.clear()


def test_interrupt_script_rejects_detached_and_unknown():
    frida_manager._sessions.clear()
    with pytest.raises(manager.AdbError, match="session not found"):
        frida_manager.interrupt_script("gone")
    frida_manager._sessions["s"] = {"detached": True, "script": MagicMock(), "session": MagicMock()}
    with pytest.raises(manager.AdbError, match="detached"):
        frida_manager.terminate_script("s")
    frida_manager._sessions.clear()


def test_post_message_forwards_to_script():
    frida_manager._sessions.clear()
    script = MagicMock()
    frida_manager._sessions["s"] = {"script": script}
    assert frida_manager.post_message("s", {"cmd": "ping"}) == {"ok": True}
    script.post.assert_called_once_with({"cmd": "ping"}, data=None)
    frida_manager._sessions.clear()


def test_post_message_decodes_hex_data():
    frida_manager._sessions.clear()
    script = MagicMock()
    frida_manager._sessions["s"] = {"script": script}
    frida_manager.post_message("s", {"cmd": "write"}, data="0a0b")
    script.post.assert_called_once_with({"cmd": "write"}, data=b"\x0a\x0b")
    frida_manager._sessions.clear()


def test_post_message_rejects_bad_hex():
    frida_manager._sessions.clear()
    frida_manager._sessions["s"] = {"script": MagicMock()}
    with pytest.raises(manager.AdbError, match="hex string"):
        frida_manager.post_message("s", {}, data="nothex")
    frida_manager._sessions.clear()


def test_post_message_rejects_detached_session():
    frida_manager._sessions.clear()
    frida_manager._sessions["s"] = {"detached": True, "script": MagicMock()}
    with pytest.raises(manager.AdbError, match="detached"):
        frida_manager.post_message("s", {})
    frida_manager._sessions.clear()


def test_detach_handler_records_reason_and_enqueues_message():
    import queue as queue_module

    frida_manager._sessions.clear()
    q = queue_module.Queue()
    frida_manager._sessions["sess1"] = {"detached": False, "detach_reason": None, "queue": q}
    handler = frida_manager._make_detach_handler("sess1", q)

    handler("application-requested")

    entry = frida_manager._sessions["sess1"]
    assert entry["detached"] is True
    assert entry["detach_reason"] == "application-requested"
    msg = q.get_nowait()["message"]
    assert msg == {"type": "detached", "reason": "application-requested"}
    frida_manager._sessions.clear()


def test_detach_handler_summarizes_crash_when_provided():
    import queue as queue_module

    frida_manager._sessions.clear()
    q = queue_module.Queue()
    frida_manager._sessions["sess1"] = {"detached": False, "detach_reason": None, "queue": q}
    handler = frida_manager._make_detach_handler("sess1", q)
    crash = types.SimpleNamespace(pid=99, process_name="com.example", summary="SIGSEGV")

    handler("process-terminated", crash)

    msg = q.get_nowait()["message"]
    assert msg["type"] == "detached"
    assert msg["reason"] == "process-terminated"
    assert msg["crash"] == {"pid": 99, "process_name": "com.example", "summary": "SIGSEGV"}
    frida_manager._sessions.clear()


def test_detach_handler_tolerates_missing_session_and_no_args():
    import queue as queue_module

    frida_manager._sessions.clear()
    q = queue_module.Queue()
    handler = frida_manager._make_detach_handler("gone", q)
    handler()  # no reason, unknown session -- must not raise
    assert q.get_nowait()["message"] == {"type": "detached", "reason": None}


def test_list_sessions_exposes_detach_state():
    frida_manager._sessions.clear()
    frida_manager._sessions["sess1"] = {
        "serial": "s1", "target": "1234", "created_at": 1.0,
        "detached": True, "detach_reason": "device-lost", "runtime": "v8",
    }
    sessions = frida_manager.list_sessions()
    assert sessions == [{
        "id": "sess1", "serial": "s1", "target": "1234", "created_at": 1.0,
        "detached": True, "detach_reason": "device-lost", "runtime": "v8",
    }]


def test_get_session_polls_is_detached():
    frida_manager._sessions.clear()
    session = MagicMock()
    session.is_detached.return_value = True
    frida_manager._sessions["s1"] = {
        "serial": "dev", "target": "1", "created_at": 2.0,
        "detached": False, "detach_reason": None, "runtime": None,
        "session": session,
    }
    result = frida_manager.get_session("s1")
    assert result["detached"] is True
    assert result["detach_reason"] == "detached"
    session.is_detached.assert_called()


def test_live_session_rejects_when_is_detached_true():
    frida_manager._sessions.clear()
    session = MagicMock()
    session.is_detached.return_value = True
    frida_manager._sessions["s1"] = {
        "detached": False, "script": MagicMock(), "session": session,
    }
    with pytest.raises(manager.AdbError, match="detached"):
        frida_manager._live_session("s1")
    frida_manager._sessions.clear()


def test_enable_and_disable_spawn_gating():
    device = MagicMock()
    with patch("adb.frida_manager._frida_device", return_value=device):
        assert frida_manager.enable_spawn_gating("s1") == {"ok": True, "spawn_gating": True}
        assert frida_manager.disable_spawn_gating("s1") == {"ok": True, "spawn_gating": False}
    device.enable_spawn_gating.assert_called_once_with()
    device.disable_spawn_gating.assert_called_once_with()


def test_enable_spawn_gating_wraps_errors():
    device = MagicMock()
    device.enable_spawn_gating.side_effect = RuntimeError("not running")
    with patch("adb.frida_manager._frida_device", return_value=device):
        with pytest.raises(manager.AdbError, match="failed to enable spawn gating"):
            frida_manager.enable_spawn_gating("s1")


def test_list_pending_spawn_sorts_by_pid():
    pending = [
        types.SimpleNamespace(pid=30, identifier="com.c"),
        types.SimpleNamespace(pid=10, identifier="com.a"),
    ]
    device = types.SimpleNamespace(enumerate_pending_spawn=lambda: pending)
    with patch("adb.frida_manager._frida_device", return_value=device):
        result = frida_manager.list_pending_spawn("s1")
    assert result == [
        {"pid": 10, "identifier": "com.a"},
        {"pid": 30, "identifier": "com.c"},
    ]


def test_list_pending_children_sorts_by_pid_with_metadata():
    pending = [
        types.SimpleNamespace(pid=30, parent_pid=5, identifier="com.c", path="/c"),
        types.SimpleNamespace(pid=10, parent_pid=5, identifier="com.a", path="/a"),
    ]
    device = types.SimpleNamespace(enumerate_pending_children=lambda: pending)
    with patch("adb.frida_manager._frida_device", return_value=device):
        result = frida_manager.list_pending_children("s1")
    assert result == [
        {"pid": 10, "parent_pid": 5, "identifier": "com.a", "path": "/a"},
        {"pid": 30, "parent_pid": 5, "identifier": "com.c", "path": "/c"},
    ]


def test_list_pending_children_wraps_errors():
    device = types.SimpleNamespace(
        enumerate_pending_children=MagicMock(side_effect=RuntimeError("nope"))
    )
    with patch("adb.frida_manager._frida_device", return_value=device):
        with pytest.raises(manager.AdbError, match="failed to list pending children"):
            frida_manager.list_pending_children("s1")


def test_set_child_gating_enable_and_disable():
    frida_manager._sessions.clear()
    _clear_device_event_state()
    session = MagicMock()
    session.is_detached.return_value = False
    device = MagicMock()
    frida_manager._sessions["s"] = {"detached": False, "session": session, "serial": "s1"}
    with patch("adb.frida_manager._frida_device", return_value=device):
        assert frida_manager.set_child_gating("s", True) == {"ok": True, "child_gating": True}
        assert frida_manager._sessions["s"]["child_gating"] is True
        session.enable_child_gating.assert_called_once_with()
        assert frida_manager.set_child_gating("s", False) == {"ok": True, "child_gating": False}
        session.disable_child_gating.assert_called_once_with()
    assert "s1" in frida_manager._wired_serials
    frida_manager._sessions.clear()
    _clear_device_event_state()


def test_set_child_gating_rejects_detached_session():
    frida_manager._sessions.clear()
    frida_manager._sessions["s"] = {"detached": True, "session": MagicMock()}
    with pytest.raises(manager.AdbError, match="detached"):
        frida_manager.set_child_gating("s", True)
    frida_manager._sessions.clear()


def test_set_child_gating_wraps_errors():
    frida_manager._sessions.clear()
    session = MagicMock()
    session.is_detached.return_value = False
    session.enable_child_gating.side_effect = RuntimeError("boom")
    frida_manager._sessions["s"] = {"detached": False, "session": session}
    with pytest.raises(manager.AdbError, match="failed to enable child gating"):
        frida_manager.set_child_gating("s", True)
    frida_manager._sessions.clear()


def test_resume_pid_calls_device_resume():
    device = MagicMock()
    with patch("adb.frida_manager._frida_device", return_value=device):
        assert frida_manager.resume_pid("s1", "1234") == {"ok": True, "pid": 1234, "resumed": True}
    device.resume.assert_called_once_with(1234)


def test_kill_pid_calls_device_kill():
    device = MagicMock()
    with patch("adb.frida_manager._frida_device", return_value=device):
        assert frida_manager.kill_pid("s1", 55) == {"ok": True, "pid": 55, "killed": True}
    device.kill.assert_called_once_with(55)


def test_resume_pid_rejects_invalid_pid():
    with patch("adb.frida_manager._frida_device", return_value=MagicMock()):
        with pytest.raises(manager.AdbError, match="invalid pid"):
            frida_manager.resume_pid("s1", "not-a-pid")
        with pytest.raises(manager.AdbError, match="invalid pid"):
            frida_manager.kill_pid("s1", 0)


def test_get_system_parameters_returns_json_safe_dict():
    params = {"os": {"id": "android", "version": "14"}, "arch": "arm64", "access": "full"}
    device = types.SimpleNamespace(query_system_parameters=lambda: params)
    with patch("adb.frida_manager._frida_device", return_value=device):
        result = frida_manager.get_system_parameters("s1")
    assert result == params


def test_get_system_parameters_wraps_errors():
    device = types.SimpleNamespace(
        query_system_parameters=MagicMock(side_effect=RuntimeError("no server"))
    )
    with patch("adb.frida_manager._frida_device", return_value=device):
        with pytest.raises(manager.AdbError, match="failed to query system parameters"):
            frida_manager.get_system_parameters("s1")


def test_get_process_by_name_returns_metadata():
    proc = types.SimpleNamespace(pid=42, name="com.example", parameters={"path": "/data/app/x", "ppid": 1})
    device = MagicMock()
    device.get_process.return_value = proc
    with patch("adb.frida_manager._frida_device", return_value=device):
        result = frida_manager.get_process("s1", "com.example")
    assert result == {"pid": 42, "name": "com.example", "parameters": {"path": "/data/app/x", "ppid": 1}}
    device.get_process.assert_called_once_with("com.example", scope="metadata")


def test_get_process_by_pid_scans_enumerate():
    procs = [
        types.SimpleNamespace(pid=10, name="a", parameters={}),
        types.SimpleNamespace(pid=42, name="com.example", parameters={"user": "u0_a1"}),
    ]
    device = MagicMock()
    device.enumerate_processes.return_value = procs
    with patch("adb.frida_manager._frida_device", return_value=device):
        result = frida_manager.get_process("s1", "42")
    assert result["pid"] == 42 and result["name"] == "com.example"
    assert result["parameters"] == {"user": "u0_a1"}


def test_get_process_missing_query_and_unknown_pid():
    device = MagicMock()
    device.enumerate_processes.return_value = []
    with patch("adb.frida_manager._frida_device", return_value=device):
        with pytest.raises(manager.AdbError, match="missing process name or pid"):
            frida_manager.get_process("s1", "")
        with pytest.raises(manager.AdbError, match="no process with pid 99"):
            frida_manager.get_process("s1", "99")


def _clear_device_event_state():
    frida_manager._wired_serials.clear()
    frida_manager._device_refs.clear()
    frida_manager._device_events.clear()


def test_spawn_process_passes_argv_env_cwd_stdio():
    device = MagicMock()
    device.spawn.return_value = 4242
    target = {
        "spawn": "com.example",
        "argv": ["--debug"],
        "envp": {"A": "1"},
        "cwd": "/data/local/tmp",
        "stdio": "pipe",
    }
    pid = frida_manager._spawn_process(device, frida_manager._normalize_spawn_target(target))
    assert pid == 4242
    device.spawn.assert_called_once_with(
        "com.example",
        argv=["--debug"],
        envp={"A": "1"},
        cwd="/data/local/tmp",
        stdio="pipe",
    )


def test_normalize_spawn_target_rejects_bad_argv_env_stdio():
    with pytest.raises(manager.AdbError, match="argv must be a list"):
        frida_manager._normalize_spawn_target({"spawn": "x", "argv": "nope"})
    with pytest.raises(manager.AdbError, match="env/envp must be an object"):
        frida_manager._normalize_spawn_target({"spawn": "x", "env": ["a"]})
    with pytest.raises(manager.AdbError, match="stdio must be"):
        frida_manager._normalize_spawn_target({"spawn": "x", "stdio": "socket"})


def test_attach_spawn_with_options(monkeypatch):
    frida_manager._sessions.clear()
    _clear_device_event_state()
    spawned = {}

    class FakeScript:
        def on(self, event, handler):
            pass

        def set_log_handler(self, handler):
            pass

        def load(self):
            pass

        def unload(self):
            pass

    class FakeSession:
        def create_script(self, source, name=None, snapshot=None, runtime=None):
            return FakeScript()

        def on(self, event, handler):
            pass

        def detach(self):
            pass

        def is_detached(self):
            return False

    class FakeDevice:
        id = "serial-1"

        def __init__(self):
            self.session = FakeSession()
            self.handlers = {}

        def on(self, signal, handler):
            self.handlers[signal] = handler

        def spawn(self, program, argv=None, envp=None, env=None, cwd=None, stdio=None, **kwargs):
            spawned["program"] = program
            spawned["argv"] = argv
            spawned["envp"] = envp
            spawned["cwd"] = cwd
            spawned["stdio"] = stdio
            return 777

        def resume(self, pid):
            spawned["resumed"] = pid

        def attach(self, target):
            spawned["attached"] = target
            return self.session

    fake_device = FakeDevice()
    fake_frida = types.SimpleNamespace(
        __version__="16.2.1",
        get_device_manager=lambda: types.SimpleNamespace(enumerate_devices=lambda: [fake_device]),
        get_usb_device=lambda timeout=5: fake_device,
    )
    monkeypatch.setitem(sys.modules, "frida", fake_frida)
    monkeypatch.setattr(frida_manager, "check_version_compatibility", lambda serial: None)

    sid = frida_manager.attach(
        "serial-1",
        {"spawn": "com.example", "argv": ["--x"], "env": {"K": "V"}, "cwd": "/tmp", "stdio": "pipe"},
        "console.log(1);",
    )
    assert spawned["program"] == "com.example"
    assert spawned["argv"] == ["--x"]
    assert spawned["envp"] == {"K": "V"}
    assert spawned["cwd"] == "/tmp"
    assert spawned["stdio"] == "pipe"
    assert spawned["attached"] == 777
    assert spawned["resumed"] == 777
    assert frida_manager._sessions[sid]["spawned_pid"] == 777
    frida_manager.detach(sid)


def test_input_to_process_sends_bytes():
    device = MagicMock()
    with patch("adb.frida_manager._frida_device", return_value=device):
        result = frida_manager.input_to_process("s1", 42, "hello")
    assert result == {"ok": True, "pid": 42, "bytes": 5}
    device.input.assert_called_once_with(42, b"hello")


def test_input_to_process_rejects_empty_and_invalid_pid():
    device = MagicMock()
    with patch("adb.frida_manager._frida_device", return_value=device):
        with pytest.raises(manager.AdbError, match="empty"):
            frida_manager.input_to_process("s1", 1, "")
        with pytest.raises(manager.AdbError, match="invalid pid"):
            frida_manager.input_to_process("s1", 0, "x")


def test_wire_device_events_records_spawn_child_crash_and_fans_out():
    frida_manager._sessions.clear()
    _clear_device_event_state()
    device = MagicMock()
    handlers = {}
    device.on.side_effect = lambda sig, h: handlers.__setitem__(sig, h)

    with patch("adb.frida_manager._frida_device", return_value=device):
        first = frida_manager.wire_device_events("s1")
        second = frida_manager.wire_device_events("s1")
    assert first == {"ok": True, "wired": True, "already": False}
    assert second["already"] is True
    assert "spawn-added" in handlers and "process-crashed" in handlers

    # Live session on same serial should receive fan-out events.
    import queue as queue_mod
    log = []
    q = queue_mod.Queue()
    frida_manager._sessions["live"] = {
        "serial": "s1",
        "detached": False,
        "queue": q,
        "log": log,
        "target": "1",
        "session": MagicMock(),
        "script": MagicMock(),
        "created_at": 0,
    }
    spawn = types.SimpleNamespace(pid=9, identifier="com.x")
    handlers["spawn-added"](spawn)
    crash = types.SimpleNamespace(pid=9, process_name="com.x", summary="SIGSEGV", report="bt")
    handlers["process-crashed"](crash)
    child = types.SimpleNamespace(pid=10, parent_pid=9, identifier="com.x", path="/system/bin/x")
    handlers["child-added"](child)

    events = frida_manager.list_device_events("s1", after_ts=0)
    types_seen = {e["type"] for e in events}
    assert types_seen >= {"spawn-added", "process-crashed", "child-added"}
    assert q.qsize() == 3
    assert len(log) == 3
    frida_manager._sessions.clear()
    _clear_device_event_state()


def test_export_session_messages_json_and_text():
    frida_manager._sessions.clear()
    frida_manager._sessions["s"] = {
        "serial": "dev",
        "target": "1",
        "detached": False,
        "detach_reason": None,
        "runtime": "qjs",
        "log": [
            {"message": {"type": "log", "level": "info", "payload": "hi"}, "data": None},
            {"message": {"type": "send", "payload": {"a": 1}}, "data": None},
            {"message": {"type": "process-crashed", "pid": 3, "process_name": "app", "summary": "boom"}, "data": None},
        ],
    }
    js = frida_manager.export_session_messages("s", "json")
    assert js["ok"] is True and js["count"] == 3 and len(js["messages"]) == 3
    txt = frida_manager.export_session_messages("s", "text")
    assert txt["format"] == "text"
    assert "info: hi" in txt["text"]
    assert "send:" in txt["text"]
    assert "crash:" in txt["text"]
    with pytest.raises(manager.AdbError, match="session not found"):
        frida_manager.export_session_messages("missing", "json")
    with pytest.raises(manager.AdbError, match="format must be"):
        frida_manager.export_session_messages("s", "xml")
    frida_manager._sessions.clear()


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
