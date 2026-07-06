import builtins
import json
import socket
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
import desktop


# --- frozen-aware path resolution ------------------------------------------

def test_is_frozen_false_in_normal_checkout(monkeypatch):
    monkeypatch.delattr(config.sys, "frozen", raising=False)
    assert config.is_frozen() is False


def test_bundle_dir_normal_checkout_is_repo_dir(monkeypatch):
    monkeypatch.delattr(config.sys, "frozen", raising=False)
    assert config.bundle_dir() == Path(config.__file__).resolve().parent


def test_bundle_dir_frozen_uses_meipass(monkeypatch, tmp_path):
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert config.bundle_dir() == tmp_path


def test_user_data_dir_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(config.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert config.user_data_dir() == tmp_path / "AdbDeviceManager"


def test_user_data_dir_macos(monkeypatch):
    monkeypatch.setattr(config.platform, "system", lambda: "Darwin")
    expected = Path.home() / "Library" / "Application Support" / "AdbDeviceManager"
    assert config.user_data_dir() == expected


def test_user_data_dir_linux_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert config.user_data_dir() == tmp_path / "adb-device-manager"


def test_user_data_dir_linux_fallback(monkeypatch):
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert config.user_data_dir() == Path.home() / ".local" / "share" / "adb-device-manager"


# --- free-port picker -------------------------------------------------------

def test_pick_free_port_is_bindable():
    port = desktop.pick_free_port()
    assert isinstance(port, int) and 1024 <= port <= 65535
    # It must actually be bindable right now (smoke test the picker's promise).
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))


# --- single-instance lock ---------------------------------------------------

def test_read_lock_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(desktop, "LOCK_PATH", tmp_path / "desktop.lock")
    assert desktop.read_lock() is None


def test_write_then_read_lock_detects_live_instance(monkeypatch, tmp_path):
    monkeypatch.setattr(desktop, "LOCK_PATH", tmp_path / "desktop.lock")
    # A real listening socket makes the port-connect probe succeed.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        (tmp_path / "desktop.lock").write_text(
            json.dumps({"pid": __import__("os").getpid(), "port": port}), encoding="utf-8")
        monkeypatch.setattr(desktop, "_pid_alive", lambda pid: True)
        info = desktop.read_lock()
        assert info is not None and info["port"] == port
    finally:
        listener.close()


def test_read_lock_stale_when_pid_dead(monkeypatch, tmp_path):
    monkeypatch.setattr(desktop, "LOCK_PATH", tmp_path / "desktop.lock")
    (tmp_path / "desktop.lock").write_text(
        json.dumps({"pid": 999999, "port": 5000}), encoding="utf-8")
    monkeypatch.setattr(desktop, "_pid_alive", lambda pid: False)
    assert desktop.read_lock() is None


def test_read_lock_stale_when_port_dead(monkeypatch, tmp_path):
    monkeypatch.setattr(desktop, "LOCK_PATH", tmp_path / "desktop.lock")
    # Reserve then release a port so nothing is listening on it -> connect fails.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    dead_port = sock.getsockname()[1]
    sock.close()
    (tmp_path / "desktop.lock").write_text(
        json.dumps({"pid": __import__("os").getpid(), "port": dead_port}), encoding="utf-8")
    monkeypatch.setattr(desktop, "_pid_alive", lambda pid: True)
    assert desktop.read_lock() is None


def test_read_lock_corrupt_file(monkeypatch, tmp_path):
    monkeypatch.setattr(desktop, "LOCK_PATH", tmp_path / "desktop.lock")
    (tmp_path / "desktop.lock").write_text("not json", encoding="utf-8")
    assert desktop.read_lock() is None


def test_clear_lock_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(desktop, "LOCK_PATH", tmp_path / "desktop.lock")
    desktop.clear_lock()  # missing -> no error
    desktop.write_lock(1234)
    assert (tmp_path / "desktop.lock").exists()
    desktop.clear_lock()
    assert not (tmp_path / "desktop.lock").exists()


# --- readiness polling -------------------------------------------------------

def test_wait_until_ready_returns_true_on_200():
    fake_resp = MagicMock(status=200)
    fake_resp.__enter__ = MagicMock(return_value=fake_resp)
    fake_resp.__exit__ = MagicMock(return_value=False)
    with patch("desktop.urllib.request.urlopen", return_value=fake_resp):
        assert desktop.wait_until_ready(12345, timeout=1.0) is True


def test_wait_until_ready_times_out_returns_false(monkeypatch):
    monkeypatch.setattr(desktop.time, "sleep", lambda _seconds: None)
    with patch("desktop.urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
        assert desktop.wait_until_ready(12345, timeout=0.01) is False


# --- main() existing-instance short circuit ---------------------------------

def test_main_returns_early_when_instance_already_running(monkeypatch, capsys):
    monkeypatch.setattr(desktop, "read_lock", lambda: {"pid": 111, "port": 4242})
    assert desktop.main() == 0
    assert "already running" in capsys.readouterr().out


def test_main_opens_pywebview_window_with_expected_url(monkeypatch):
    monkeypatch.setattr(desktop, "read_lock", lambda: None)
    monkeypatch.setattr(desktop.auth, "ensure_password", lambda: None)
    monkeypatch.setattr(desktop, "pick_free_port", lambda: 54321)
    monkeypatch.setattr(desktop.threading, "Thread", lambda target, args=(), daemon=None: MagicMock(start=lambda: None))
    monkeypatch.setattr(desktop, "wait_until_ready", lambda port: True)
    monkeypatch.setattr(desktop, "write_lock", lambda port: None)
    monkeypatch.setattr(desktop, "clear_lock", lambda: None)

    fake_webview = MagicMock()
    monkeypatch.setitem(sys.modules, "webview", fake_webview)

    assert desktop.main() == 0

    fake_webview.create_window.assert_called_once_with(
        desktop.WINDOW_TITLE, "http://127.0.0.1:54321/", width=1280, height=860
    )
    fake_webview.start.assert_called_once()


def test_main_falls_back_to_browser_when_pywebview_missing(monkeypatch):
    monkeypatch.setattr(desktop, "read_lock", lambda: None)
    monkeypatch.setattr(desktop.auth, "ensure_password", lambda: None)
    monkeypatch.setattr(desktop, "pick_free_port", lambda: 54322)
    monkeypatch.setattr(desktop.threading, "Thread", lambda target, args=(), daemon=None: MagicMock(start=lambda: None))
    monkeypatch.setattr(desktop, "wait_until_ready", lambda port: True)
    monkeypatch.setattr(desktop, "write_lock", lambda port: None)
    monkeypatch.setattr(desktop, "clear_lock", lambda: None)
    monkeypatch.delitem(sys.modules, "webview", raising=False)

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "webview":
            raise ImportError("no pywebview")
        return real_import(name, *args, **kwargs)

    opened = {}
    fake_webbrowser = MagicMock()
    fake_webbrowser.open.side_effect = lambda url: opened.setdefault("url", url)
    monkeypatch.setitem(sys.modules, "webbrowser", fake_webbrowser)
    monkeypatch.setattr(desktop.time, "sleep", MagicMock(side_effect=KeyboardInterrupt))

    with patch("builtins.__import__", side_effect=fake_import):
        assert desktop.main() == 0

    assert opened["url"] == "http://127.0.0.1:54322/"
    fake_webbrowser.open.assert_called_once()
