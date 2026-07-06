import sys
import types

import pytest

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
