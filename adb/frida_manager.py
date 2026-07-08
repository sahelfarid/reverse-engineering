"""Frida server provisioning, script storage, and live session registry."""
from __future__ import annotations

import hashlib
import importlib
import lzma
import queue
import re
import threading
import time
import uuid
from pathlib import Path

import requests

import config
from . import devices, manager, process_manager

FRIDA_SERVER_REMOTE = "/data/local/tmp/frida-server"
FRIDA_PID_REMOTE = "/data/local/tmp/frida-server.pid"
MAX_SCRIPT_BYTES = 256 * 1024

_ABI_ARCH = {
    "armeabi-v7a": "arm",
    "armeabi": "arm",
    "arm64-v8a": "arm64",
    "x86": "x86",
    "x86_64": "x86_64",
}
_SCRIPT_NAME_RE = re.compile(r"^[A-Za-z0-9_. -]{1,80}$")
_sessions: dict[str, dict] = {}
_sessions_lock = threading.Lock()
_server_pids: dict[str, str] = {}


DEFAULT_SCRIPTS = {
    "template-method-tracer": {
        "readonly": True,
        "description": "Authorized testing template: trace a method in your own app.",
        "source": """// Authorized testing only: edit className and methodName for your own app.
Java.perform(function () {
  const className = "com.example.TargetClass";
  const methodName = "targetMethod";
  const Target = Java.use(className);
  Target[methodName].overloads.forEach(function (overload) {
    overload.implementation = function () {
      const args = Array.prototype.slice.call(arguments).map(String);
      console.log(className + "." + methodName + "(" + args.join(", ") + ")");
      const ret = overload.apply(this, arguments);
      console.log("return => " + ret);
      return ret;
    };
  });
});
""",
    },
    "template-root-detection-checks": {
        "readonly": True,
        "description": "Defensive test template for validating root-detection behavior in your own app.",
        "source": """// Authorized defensive testing only: verify your own app's root-detection controls.
Java.perform(function () {
  const File = Java.use("java.io.File");
  const exists = File.exists.overload();
  const suspicious = ["/system/xbin/su", "/system/bin/su", "/sbin/su", "/su/bin/su"];
  exists.implementation = function () {
    const path = this.getAbsolutePath();
    if (suspicious.indexOf(path) !== -1) {
      console.log("root check File.exists blocked for " + path);
      return false;
    }
    return exists.call(this);
  };
});
""",
    },
    "template-ssl-pinning-lab": {
        "readonly": True,
        "description": "Authorized proxy testing template for your own app and lab traffic.",
        "source": """// Authorized testing only: use with your own app to validate proxy-based traffic inspection.
Java.perform(function () {
  const X509TrustManager = Java.use("javax.net.ssl.X509TrustManager");
  console.log("Load a focused SSL-pinning hook for the framework your own app uses.");
  send({ type: "notice", message: "Starter loaded; tailor this to your app's networking stack." });
});
""",
    },
}


def _import_frida():
    try:
        return importlib.import_module("frida")
    except ImportError:
        return None


def _frida_version() -> str | None:
    frida = _import_frida()
    return getattr(frida, "__version__", None) if frida else None


_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _parse_version(value: str | None) -> tuple[int, int, int] | None:
    match = _VERSION_RE.search(value or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def get_server_version(serial: str) -> str | None:
    """Return the version reported by the on-device frida-server, or None.

    Runs `frida-server --version`; this only prints a string and does not need
    root, so it works whenever the binary has been pushed and is executable.
    """
    if not _is_pushed(serial):
        return None
    stdout, _stderr, rc = manager.shell(serial, f"{FRIDA_SERVER_REMOTE} --version 2>/dev/null", timeout=8)
    if rc != 0:
        return None
    parsed = _parse_version(stdout)
    return ".".join(str(part) for part in parsed) if parsed else None


def versions_compatible(client_version: str | None, server_version: str | None) -> bool:
    """Frida's wire protocol is tied to major.minor; a mismatch there breaks attach.

    Returns True when we cannot determine one side (so we never block on missing
    information) and only False on a confirmed major.minor divergence.
    """
    client = _parse_version(client_version)
    server = _parse_version(server_version)
    if not client or not server:
        return True
    return client[:2] == server[:2]


def check_version_compatibility(serial: str) -> None:
    """Raise AdbError with a clear message when client/server versions diverge."""
    client_version = _frida_version()
    server_version = get_server_version(serial)
    if not versions_compatible(client_version, server_version):
        raise manager.AdbError(
            "frida version mismatch: python frida "
            f"{client_version} vs frida-server {server_version}. "
            "Restart the server after pushing a matching build "
            "(Push server re-downloads the version matching the installed package)."
        )


def _script_dir() -> Path:
    path = config.DATA_DIR / "frida_scripts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_script_name(name: str) -> str:
    name = str(name or "").strip()
    if not _SCRIPT_NAME_RE.match(name) or "/" in name or "\\" in name or ".." in name:
        raise manager.AdbError("invalid script name")
    return name[:-3] if name.endswith(".js") else name


def resolve_frida_server_url(frida_version: str, abi: str) -> str:
    arch = _ABI_ARCH.get((abi or "").strip())
    if not arch:
        raise manager.AdbError(f"Unsupported Android ABI for frida-server: {abi or 'unknown'}")
    return (
        f"https://github.com/frida/frida/releases/download/{frida_version}/"
        f"frida-server-{frida_version}-android-{arch}.xz"
    )


def _server_path(frida_version: str, abi: str) -> Path:
    arch = _ABI_ARCH.get((abi or "").strip())
    if not arch:
        raise manager.AdbError(f"Unsupported Android ABI for frida-server: {abi or 'unknown'}")
    return config.VENDOR_DIR / "frida" / frida_version / arch / "frida-server"


def ensure_frida_server(serial: str) -> Path:
    frida_version = _frida_version()
    if not frida_version:
        raise manager.AdbError("frida package not installed")
    abi = devices.get_basic_properties(serial).get("abi")
    url = resolve_frida_server_url(frida_version, abi)
    dest = _server_path(frida_version, abi)
    if dest.is_file():
        return dest

    compressed = dest.with_suffix(".xz")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with requests.get(url, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(compressed, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    if chunk:
                        fh.write(chunk)
        with lzma.open(compressed, "rb") as src, open(dest, "wb") as out:
            out.write(src.read())
    except requests.RequestException as exc:
        raise manager.AdbError(f"Failed to download frida-server: {exc}") from exc
    finally:
        if compressed.exists():
            compressed.unlink()
    return dest


def _is_pushed(serial: str) -> bool:
    stdout, _stderr, rc = manager.shell(serial, f"test -x {FRIDA_SERVER_REMOTE} && echo yes", timeout=5)
    return rc == 0 and "yes" in stdout


def _running_pid(serial: str) -> str | None:
    pid = _server_pids.get(serial)
    if not pid:
        stdout, _stderr, rc = manager.shell(serial, f"cat {FRIDA_PID_REMOTE} 2>/dev/null", timeout=5)
        pid = stdout.strip().splitlines()[-1] if rc == 0 and stdout.strip() else None
    if not pid or not pid.isdigit():
        return None
    _stdout, _stderr, rc = manager.shell(serial, f"su -c {manager.quote_remote(f'kill -0 {pid}')}", timeout=5)
    return pid if rc == 0 else None


def get_status() -> dict:
    version = _frida_version()
    result = {
        "ok": True,
        "python_installed": bool(version),
        "python_version": version,
        "devices": [],
    }
    try:
        connected = devices.list_devices()
    except manager.AdbError:
        connected = []
    for device in connected:
        if device.get("state") != "device":
            continue
        serial = device["serial"]
        try:
            props = devices.get_basic_properties(serial)
            abi = props.get("abi")
            cached = bool(version and _server_path(version, abi).is_file())
            root = manager.has_root_shell(serial)
            pushed = _is_pushed(serial)
            running_pid = _running_pid(serial) if root else None
            server_version = get_server_version(serial) if pushed else None
            result["devices"].append({
                "serial": serial,
                "abi": abi,
                "root_available": root,
                "server_cached": cached,
                "server_pushed": pushed,
                "server_running": bool(running_pid),
                "pid": running_pid,
                "server_version": server_version,
                "version_match": versions_compatible(version, server_version),
            })
        except manager.AdbError as exc:
            result["devices"].append({"serial": serial, "error": str(exc)})
    return result


def push_server(serial: str) -> dict:
    if not manager.has_root_shell(serial):
        raise manager.AdbError("device must be rooted to run classic frida-server")
    local_server = ensure_frida_server(serial)
    proc = manager.run(["-s", serial, "push", str(local_server), FRIDA_SERVER_REMOTE], timeout=120)
    if proc.returncode != 0:
        raise manager.AdbError(proc.stderr.strip() or "adb push failed")
    _stdout, stderr, rc = manager.shell(serial, f"chmod 755 {FRIDA_SERVER_REMOTE}", timeout=10)
    if rc != 0:
        raise manager.AdbError(stderr.strip() or "chmod failed")
    return {"ok": True, "remote_path": FRIDA_SERVER_REMOTE}


def start_server(serial: str) -> dict:
    if not manager.has_root_shell(serial):
        raise manager.AdbError("device must be rooted to run classic frida-server")
    if not _is_pushed(serial):
        push_server(serial)
    existing = _running_pid(serial)
    if existing:
        return {"ok": True, "pid": existing, "already_running": True}
    remote = f"{FRIDA_SERVER_REMOTE} >/data/local/tmp/frida-server.log 2>&1 & echo $! > {FRIDA_PID_REMOTE}"
    _stdout, stderr, rc = manager.shell(serial, f"su -c {manager.quote_remote(remote)}", timeout=10)
    if rc != 0:
        raise manager.AdbError(stderr.strip() or "failed to start frida-server")
    time.sleep(0.3)
    pid = _running_pid(serial)
    if not pid:
        raise manager.AdbError("frida-server did not report a running pid")
    _server_pids[serial] = pid
    return {"ok": True, "pid": pid}


def push_and_start_server(serial: str) -> dict:
    push = push_server(serial)
    start = start_server(serial)
    return {"ok": True, "push": push, "pid": start.get("pid")}


def stop_server(serial: str) -> dict:
    pid = _running_pid(serial)
    if not pid:
        return {"ok": True, "stopped": False}
    _stdout, stderr, rc = manager.shell(serial, f"su -c {manager.quote_remote(f'kill -9 {pid}')}", timeout=10)
    if rc != 0:
        raise manager.AdbError(stderr.strip() or f"failed to stop pid {pid}")
    manager.shell(serial, f"rm -f {FRIDA_PID_REMOTE}", timeout=5)
    _server_pids.pop(serial, None)
    return {"ok": True, "stopped": True, "pid": pid}


def _frida_device(serial: str | None = None):
    frida = _import_frida()
    if not frida:
        raise manager.AdbError("frida package not installed")
    dm = frida.get_device_manager()
    if serial:
        for device in dm.enumerate_devices():
            if getattr(device, "id", None) == serial:
                return device
    return frida.get_usb_device(timeout=5)


def list_processes(serial: str) -> list[dict]:
    try:
        device = _frida_device(serial)
        return sorted(
            [{"pid": p.pid, "name": p.name} for p in device.enumerate_processes()],
            key=lambda p: (str(p["name"]).lower(), p["pid"]),
        )
    except Exception:
        return process_manager.list_processes(serial).get("processes", [])


def _application_public(app) -> dict:
    pid = getattr(app, "pid", 0) or 0
    return {
        "identifier": getattr(app, "identifier", None),
        "name": getattr(app, "name", None),
        "pid": pid or None,
        "running": bool(pid),
    }


def list_applications(serial: str) -> list[dict]:
    """List installed applications (not just running processes).

    Requires a live frida-server; unlike list_processes() there is no ADB
    fallback because the app identifier/running metadata comes from Frida.
    """
    device = _frida_device(serial)
    try:
        apps = device.enumerate_applications()
    except Exception as exc:
        raise manager.AdbError(f"failed to enumerate applications: {exc}") from exc
    return sorted(
        (_application_public(app) for app in apps),
        key=lambda a: (not a["running"], str(a["name"] or a["identifier"] or "").lower()),
    )


def get_frontmost_application(serial: str) -> dict | None:
    """Return the currently foregrounded application, or None if none is."""
    device = _frida_device(serial)
    try:
        app = device.get_frontmost_application()
    except Exception as exc:
        raise manager.AdbError(f"failed to query frontmost application: {exc}") from exc
    return _application_public(app) if app else None


def _session_public(session_id: str, entry: dict) -> dict:
    return {
        "id": session_id,
        "serial": entry["serial"],
        "target": entry["target"],
        "created_at": entry["created_at"],
        "detached": entry.get("detached", False),
        "detach_reason": entry.get("detach_reason"),
    }


def _summarize_crash(crash) -> dict | None:
    if crash is None:
        return None
    return {
        "pid": getattr(crash, "pid", None),
        "process_name": getattr(crash, "process_name", None),
        "summary": getattr(crash, "summary", None),
    }


def _make_detach_handler(session_id: str, messages: "queue.Queue"):
    """Frida fires 'detached' with (reason[, crash]); surface it to the stream.

    Signature varies across frida versions (some omit crash), so accept *args.
    """
    def on_detached(*args):
        reason = args[0] if args else None
        crash = _summarize_crash(args[1]) if len(args) > 1 else None
        with _sessions_lock:
            entry = _sessions.get(session_id)
            if entry:
                entry["detached"] = True
                entry["detach_reason"] = reason
        payload = {"type": "detached", "reason": reason}
        if crash:
            payload["crash"] = crash
        messages.put({"message": payload, "data": None})
    return on_detached


def list_sessions() -> list[dict]:
    with _sessions_lock:
        return [_session_public(sid, entry) for sid, entry in _sessions.items()]


def attach(serial: str, target, script_source: str) -> str:
    if not script_source or len(script_source.encode("utf-8")) > MAX_SCRIPT_BYTES:
        raise manager.AdbError("script source is empty or too large")
    check_version_compatibility(serial)
    device = _frida_device(serial)
    spawned_pid = None
    if isinstance(target, dict):
        if target.get("spawn"):
            spawned_pid = device.spawn([str(target["spawn"])])
            attach_target = spawned_pid
        else:
            attach_target = target.get("pid") or target.get("name")
    else:
        attach_target = int(target) if str(target).isdigit() else str(target)
    if not attach_target:
        raise manager.AdbError("missing attach target")

    session = device.attach(attach_target)
    script = session.create_script(script_source)
    messages: queue.Queue = queue.Queue()

    def on_message(message, data):
        messages.put({"message": message, "data": data.decode("utf-8", errors="replace") if data else None})

    script.on("message", on_message)
    script.load()
    if spawned_pid is not None:
        device.resume(spawned_pid)

    session_id = uuid.uuid4().hex[:12]
    with _sessions_lock:
        _sessions[session_id] = {
            "serial": serial,
            "target": target,
            "session": session,
            "script": script,
            "queue": messages,
            "created_at": time.time(),
            "detached": False,
            "detach_reason": None,
        }
    try:
        session.on("detached", _make_detach_handler(session_id, messages))
    except Exception:
        pass  # signal wiring is best-effort; the session still works without it
    return session_id


def stream_messages(session_id: str):
    with _sessions_lock:
        entry = _sessions.get(session_id)
    if not entry:
        raise manager.AdbError("session not found")
    q = entry["queue"]
    while True:
        try:
            yield q.get(timeout=15)
        except queue.Empty:
            yield {"message": {"type": "heartbeat"}}


def drain_messages(session_id: str, duration_sec: float) -> list[dict]:
    """Collect all messages a session's script emits over a fixed window.

    Unlike stream_messages() (which yields forever with heartbeats for an SSE
    client), this is for callers that spawn+observe+detach synchronously
    within a single request and just want "everything the script said in the
    next N seconds".
    """
    with _sessions_lock:
        entry = _sessions.get(session_id)
    if not entry:
        raise manager.AdbError("session not found")
    q = entry["queue"]
    deadline = time.time() + duration_sec
    collected: list[dict] = []
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        try:
            collected.append(q.get(timeout=remaining))
        except queue.Empty:
            break
    return collected


def detach(session_id: str) -> dict:
    with _sessions_lock:
        entry = _sessions.pop(session_id, None)
    if not entry:
        return {"ok": True, "detached": False}
    try:
        entry["script"].unload()
    finally:
        entry["session"].detach()
    return {"ok": True, "detached": True}


def script_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def list_scripts() -> dict:
    scripts = dict(DEFAULT_SCRIPTS)
    for path in sorted(_script_dir().glob("*.js")):
        name = path.stem
        scripts[name] = {
            "readonly": False,
            "description": "Saved script",
            "source": path.read_text(encoding="utf-8"),
        }
    return scripts


def save_script(name: str, source: str) -> dict:
    name = validate_script_name(name)
    if name in DEFAULT_SCRIPTS:
        raise manager.AdbError("default scripts are read-only")
    if not source or len(source.encode("utf-8")) > MAX_SCRIPT_BYTES:
        raise manager.AdbError("script source is empty or too large")
    (_script_dir() / f"{name}.js").write_text(source, encoding="utf-8")
    return {"ok": True, "name": name}


def delete_script(name: str) -> dict:
    name = validate_script_name(name)
    if name in DEFAULT_SCRIPTS:
        raise manager.AdbError("default scripts are read-only")
    path = _script_dir() / f"{name}.js"
    if path.exists():
        path.unlink()
    return {"ok": True}
