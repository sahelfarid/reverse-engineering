"""Desktop shell around the existing Flask panel.

Runs the unchanged `app.create_app()` server on a background thread bound to a
free loopback port, then points a native OS webview (pywebview: WebView2 /
WKWebView / WebKitGTK) at it. This is a thin wrapper -- no routes, templates,
or trust boundaries change; the window is just another local HTTP client.

Run: `python desktop.py`  (or the PyInstaller-built executable).
Server-only deployments keep using `python app.py`.
"""
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

import config

WINDOW_TITLE = "ADB Device Manager"
LOCK_PATH = config.DATA_DIR / "desktop.lock"
READY_PATH = "/api/adb/status"  # exists, needs no auth -- safe readiness probe


def pick_free_port() -> int:
    """Ask the OS for an unused loopback port and return it.

    Binding to port 0 lets the kernel assign a free port; we read it back and
    release it. There's a tiny race between release and re-bind, but it avoids
    the far more common collision of hardcoding 5000 while a stale instance
    still holds it.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _pid_alive(pid: int) -> bool:
    """Best-effort liveness check without a hard psutil dependency."""
    try:
        import psutil  # optional; present in requirements-desktop.txt
        return psutil.pid_exists(pid)
    except ImportError:
        pass
    if os.name == "nt":
        # No cheap portable check on Windows without psutil; assume alive so a
        # real running instance is never stomped. Stale locks are cleared by
        # the connect-probe in read_lock() below instead.
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_lock() -> dict | None:
    """Return {pid, port} of a live instance, or None if no/stale lock.

    A lock is only honoured if its PID is alive AND its port actually accepts a
    connection -- this clears stale locks left by a crashed previous run even on
    platforms where the PID check is unreliable.
    """
    if not LOCK_PATH.exists():
        return None
    try:
        info = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        pid, port = int(info["pid"]), int(info["port"])
    except (json.JSONDecodeError, OSError, KeyError, ValueError, TypeError):
        return None
    if not _pid_alive(pid):
        return None
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        if sock.connect_ex(("127.0.0.1", port)) != 0:
            return None  # port dead -> stale lock
    return {"pid": pid, "port": port}


def write_lock(port: int) -> None:
    LOCK_PATH.write_text(json.dumps({"pid": os.getpid(), "port": port}), encoding="utf-8")


def clear_lock() -> None:
    try:
        LOCK_PATH.unlink()
    except FileNotFoundError:
        pass


def wait_until_ready(port: int, timeout: float = 20.0) -> bool:
    """Poll the readiness endpoint until the server answers or we time out."""
    url = f"http://127.0.0.1:{port}{READY_PATH}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.15)
    return False


def run_server(port: int) -> None:
    from app import create_app
    server = create_app()
    # threaded: SSE (logcat) + background jobs need concurrent requests.
    server.run(host="127.0.0.1", port=port, threaded=True, debug=False, use_reloader=False)


def main() -> int:
    existing = read_lock()
    if existing is not None:
        print(f"ADB Device Manager is already running (pid {existing['pid']}, "
              f"port {existing['port']}). Open http://127.0.0.1:{existing['port']}/")
        return 0

    # No first-run password is generated here anymore -- the first-launch
    # setup screen (served by routes.core.index()) lets the user set one
    # (or explicitly skip) from the browser instead of reading it off stdout.
    port = pick_free_port()
    threading.Thread(target=run_server, args=(port,), daemon=True).start()

    if not wait_until_ready(port):
        print("Server did not become ready in time; aborting.", file=sys.stderr)
        return 1

    write_lock(port)
    try:
        import webview
        webview.create_window(WINDOW_TITLE, f"http://127.0.0.1:{port}/", width=1280, height=860)
        webview.start()
    except ImportError:
        # pywebview not installed (e.g. running desktop.py in a headless/dev
        # env): fall back to the default browser so the app is still usable.
        import webbrowser
        print(f"pywebview not installed; opening in browser: http://127.0.0.1:{port}/")
        webbrowser.open(f"http://127.0.0.1:{port}/")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    finally:
        clear_lock()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
