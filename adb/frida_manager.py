"""Frida server provisioning, script storage, and live session registry."""
from __future__ import annotations

import hashlib
import importlib
import json
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
    "template-root-detection-bypass": {
        "readonly": True,
        "description": "Authorized defensive testing: neutralize common root-detection checks in your own app to validate the controls.",
        "source": """// Authorized defensive testing only: verify your own app's root-detection controls.
// Each hook is wrapped so a class the app does not use is silently skipped.
Java.perform(function () {
  function tryHook(name, fn) {
    try { fn(); console.log("[root] hooked " + name); }
    catch (e) { /* class/method not present in this app */ }
  }

  var suspiciousPaths = [
    "/system/app/Superuser.apk", "/sbin/su", "/system/bin/su", "/system/xbin/su",
    "/data/local/xbin/su", "/data/local/bin/su", "/system/sd/xbin/su",
    "/system/bin/failsafe/su", "/data/local/su", "/su/bin/su",
    "/system/xbin/busybox", "/system/bin/magisk", "/sbin/magisk", "/data/adb/magisk"
  ];
  var suspiciousPackages = [
    "com.topjohnwu.magisk", "eu.chainfire.supersu",
    "com.noshufou.android.su", "com.koushikdutta.superuser"
  ];

  tryHook("File.exists", function () {
    var File = Java.use("java.io.File");
    File.exists.implementation = function () {
      var path = this.getAbsolutePath();
      if (suspiciousPaths.indexOf(path) !== -1) {
        send({ type: "root-bypass", check: "File.exists", path: String(path) });
        return false;
      }
      return this.exists();  // Frida routes this to the original implementation
    };
  });

  tryHook("Runtime.exec(String)", function () {
    var Runtime = Java.use("java.lang.Runtime");
    Runtime.exec.overload("java.lang.String").implementation = function (cmd) {
      if (String(cmd).indexOf("su") !== -1 || String(cmd).indexOf("which") !== -1 || String(cmd).indexOf("busybox") !== -1) {
        send({ type: "root-bypass", check: "Runtime.exec", cmd: String(cmd) });
        return this.exec("echo");
      }
      return this.exec(cmd);
    };
  });

  tryHook("SystemProperties.get", function () {
    var SP = Java.use("android.os.SystemProperties");
    SP.get.overload("java.lang.String").implementation = function (key) {
      var value = this.get(key);
      if (key === "ro.build.tags") return "release-keys";
      if (key === "ro.debuggable" || key === "ro.secure") return key === "ro.secure" ? "1" : "0";
      return value;
    };
  });

  tryHook("Build.TAGS", function () {
    Java.use("android.os.Build").TAGS.value = "release-keys";
  });

  tryHook("PackageManager.getPackageInfo (su managers)", function () {
    var PM = Java.use("android.app.ApplicationPackageManager");
    var NameNotFound = Java.use("android.content.pm.PackageManager$NameNotFoundException");
    PM.getPackageInfo.overload("java.lang.String", "int").implementation = function (pkg, flags) {
      if (suspiciousPackages.indexOf(String(pkg)) !== -1) {
        send({ type: "root-bypass", check: "getPackageInfo", package: String(pkg) });
        throw NameNotFound.$new(String(pkg));
      }
      return this.getPackageInfo(pkg, flags);
    };
  });

  tryHook("RootBeer.*", function () {
    var RootBeer = Java.use("com.scottyab.rootbeer.RootBeer");
    ["isRooted", "isRootedWithoutBusyBoxCheck", "checkForBinary",
     "detectRootManagementApps", "detectPotentiallyDangerousApps",
     "checkForSuBinary", "checkForDangerousProps", "checkForRWPaths"].forEach(function (m) {
      try {
        RootBeer[m].overloads.forEach(function (ov) { ov.implementation = function () { return false; }; });
      } catch (e) {}
    });
  });

  send({ type: "notice", message: "Root-detection bypass hooks installed (authorized testing only)." });
});
""",
    },
    "template-ssl-pinning-bypass": {
        "readonly": True,
        "description": "Authorized proxy testing: unpin TLS across common frameworks (OkHttp, Conscrypt, custom TrustManager, WebView) in your own app.",
        "source": """// Authorized testing only: unpin TLS in your OWN app to inspect its traffic through a lab proxy.
// Each framework hook is guarded so unused stacks are skipped cleanly.
Java.perform(function () {
  function tryHook(name, fn) {
    try { fn(); console.log("[ssl] hooked " + name); }
    catch (e) { /* framework not present in this app */ }
  }

  tryHook("OkHttp3 CertificatePinner.check", function () {
    var CertificatePinner = Java.use("okhttp3.CertificatePinner");
    CertificatePinner.check.overload("java.lang.String", "java.util.List").implementation = function (host, peerCertificates) {
      send({ type: "ssl-bypass", framework: "okhttp3", host: String(host) });
      return;
    };
    try {
      CertificatePinner.check.overload("java.lang.String", "[Ljava.security.cert.Certificate;").implementation = function () { return; };
    } catch (e) {}
  });

  tryHook("Conscrypt TrustManagerImpl.verifyChain", function () {
    var TrustManagerImpl = Java.use("com.android.org.conscrypt.TrustManagerImpl");
    TrustManagerImpl.verifyChain.implementation = function (untrustedChain, trustAnchorChain, host, clientAuth, ocspData, tlsSctData) {
      send({ type: "ssl-bypass", framework: "conscrypt", host: String(host) });
      return untrustedChain;
    };
  });

  tryHook("Conscrypt TrustManagerImpl.checkTrustedRecursive", function () {
    var TrustManagerImpl = Java.use("com.android.org.conscrypt.TrustManagerImpl");
    var ArrayList = Java.use("java.util.ArrayList");
    TrustManagerImpl.checkTrustedRecursive.implementation = function () {
      return ArrayList.$new();
    };
  });

  tryHook("SSLContext.init (custom TrustManager)", function () {
    var X509TrustManager = Java.use("javax.net.ssl.X509TrustManager");
    var SSLContext = Java.use("javax.net.ssl.SSLContext");
    var TrustAll = Java.registerClass({
      name: "org.authtest.TrustAllManager",
      implements: [X509TrustManager],
      methods: {
        checkClientTrusted: function (chain, authType) {},
        checkServerTrusted: function (chain, authType) {},
        getAcceptedIssuers: function () { return []; }
      }
    });
    var init = SSLContext.init.overload(
      "[Ljavax.net.ssl.KeyManager;", "[Ljavax.net.ssl.TrustManager;", "java.security.SecureRandom");
    init.implementation = function (km, tm, sr) {
      send({ type: "ssl-bypass", framework: "sslcontext" });
      init.call(this, km, [TrustAll.$new()], sr);
    };
  });

  tryHook("WebViewClient.onReceivedSslError", function () {
    var WebViewClient = Java.use("android.webkit.WebViewClient");
    WebViewClient.onReceivedSslError.overload(
      "android.webkit.WebView", "android.webkit.SslErrorHandler", "android.net.http.SslError")
      .implementation = function (view, handler, error) {
        send({ type: "ssl-bypass", framework: "webview" });
        handler.proceed();
      };
  });

  send({ type: "notice", message: "SSL unpinning hooks installed (authorized testing only)." });
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


def _require_pid(pid) -> int:
    try:
        value = int(pid)
    except (TypeError, ValueError) as exc:
        raise manager.AdbError("invalid pid") from exc
    if value <= 0:
        raise manager.AdbError("invalid pid")
    return value


def enable_spawn_gating(serial: str) -> dict:
    """Suspend every newly spawned process so it can be hooked before it runs."""
    device = _frida_device(serial)
    try:
        device.enable_spawn_gating()
    except Exception as exc:
        raise manager.AdbError(f"failed to enable spawn gating: {exc}") from exc
    return {"ok": True, "spawn_gating": True}


def disable_spawn_gating(serial: str) -> dict:
    device = _frida_device(serial)
    try:
        device.disable_spawn_gating()
    except Exception as exc:
        raise manager.AdbError(f"failed to disable spawn gating: {exc}") from exc
    return {"ok": True, "spawn_gating": False}


def list_pending_spawn(serial: str) -> list[dict]:
    """List processes suspended by spawn gating, awaiting resume or kill."""
    device = _frida_device(serial)
    try:
        pending = device.enumerate_pending_spawn()
    except Exception as exc:
        raise manager.AdbError(f"failed to list pending spawn: {exc}") from exc
    return sorted(
        ({"pid": s.pid, "identifier": getattr(s, "identifier", None)} for s in pending),
        key=lambda s: s["pid"],
    )


def list_pending_children(serial: str) -> list[dict]:
    """List child processes suspended by child gating, awaiting resume or kill."""
    device = _frida_device(serial)
    try:
        pending = device.enumerate_pending_children()
    except Exception as exc:
        raise manager.AdbError(f"failed to list pending children: {exc}") from exc
    return sorted(
        ({
            "pid": c.pid,
            "parent_pid": getattr(c, "parent_pid", None),
            "identifier": getattr(c, "identifier", None),
            "path": getattr(c, "path", None),
        } for c in pending),
        key=lambda c: c["pid"],
    )


def resume_pid(serial: str, pid) -> dict:
    """Resume a suspended (spawn-gated or freshly spawned) process."""
    device = _frida_device(serial)
    value = _require_pid(pid)
    try:
        device.resume(value)
    except Exception as exc:
        raise manager.AdbError(f"failed to resume pid {value}: {exc}") from exc
    return {"ok": True, "pid": value, "resumed": True}


def kill_pid(serial: str, pid) -> dict:
    """Kill a process on the device via the Frida device API."""
    device = _frida_device(serial)
    value = _require_pid(pid)
    try:
        device.kill(value)
    except Exception as exc:
        raise manager.AdbError(f"failed to kill pid {value}: {exc}") from exc
    return {"ok": True, "pid": value, "killed": True}


def get_system_parameters(serial: str) -> dict:
    """Return the device details Frida reports (os, arch, platform, access, name)."""
    device = _frida_device(serial)
    try:
        params = device.query_system_parameters()
    except Exception as exc:
        raise manager.AdbError(f"failed to query system parameters: {exc}") from exc
    return _json_safe(dict(params or {}))


def get_process(serial: str, query) -> dict:
    """Fetch a single process (by name or pid) with metadata (path, ppid, user).

    Name lookup uses device.get_process(); a numeric query is resolved against
    enumerate_processes() since the Frida API matches processes by name only.
    """
    device = _frida_device(serial)
    q = str(query or "").strip()
    if not q:
        raise manager.AdbError("missing process name or pid")
    try:
        if q.isdigit():
            pid = int(q)
            try:
                procs = device.enumerate_processes(scope="metadata")
            except TypeError:
                procs = device.enumerate_processes()
            proc = next((p for p in procs if p.pid == pid), None)
            if proc is None:
                raise manager.AdbError(f"no process with pid {pid}")
        else:
            try:
                proc = device.get_process(q, scope="metadata")
            except TypeError:
                proc = device.get_process(q)
    except manager.AdbError:
        raise
    except Exception as exc:
        raise manager.AdbError(f"process lookup failed: {exc}") from exc
    return {
        "pid": proc.pid,
        "name": proc.name,
        "parameters": _json_safe(dict(getattr(proc, "parameters", None) or {})),
    }


def _refresh_detach_state(entry: dict) -> None:
    """Poll Frida's is_detached() so list/get reflect reality without waiting for the signal."""
    if entry.get("detached"):
        return
    session = entry.get("session")
    if session is None:
        return
    try:
        live_detached = bool(session.is_detached())
    except Exception:
        return
    if live_detached:
        entry["detached"] = True
        if not entry.get("detach_reason"):
            entry["detach_reason"] = "detached"


def _session_public(session_id: str, entry: dict) -> dict:
    _refresh_detach_state(entry)
    return {
        "id": session_id,
        "serial": entry["serial"],
        "target": entry["target"],
        "created_at": entry["created_at"],
        "detached": entry.get("detached", False),
        "detach_reason": entry.get("detach_reason"),
        "runtime": entry.get("runtime"),
    }


def get_session(session_id: str) -> dict:
    """Return one session's public state, refreshing is_detached() first."""
    with _sessions_lock:
        entry = _sessions.get(session_id)
        if not entry:
            raise manager.AdbError("session not found")
        return _session_public(session_id, entry)


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


_VALID_RUNTIMES = frozenset({"qjs", "v8"})
_MAX_PARAMS_BYTES = 16 * 1024


def inject_script_params(script_source: str, params: dict | None) -> str:
    """Prepend `const PARAMS = {...};` so agents can read named load-time parameters.

    `params` must be a JSON object (dict). Nested structures are allowed; values are
    serialized with json.dumps. Empty/None params leave the source unchanged.
    """
    if not params:
        return script_source
    if not isinstance(params, dict):
        raise manager.AdbError("params must be a JSON object")
    try:
        encoded = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise manager.AdbError(f"params are not JSON-serializable: {exc}") from exc
    if len(encoded.encode("utf-8")) > _MAX_PARAMS_BYTES:
        raise manager.AdbError("params payload is too large")
    prelude = f"const PARAMS = {encoded};\n"
    combined = prelude + script_source
    if len(combined.encode("utf-8")) > MAX_SCRIPT_BYTES:
        raise manager.AdbError("script source is empty or too large")
    return combined


def attach(
    serial: str,
    target,
    script_source: str,
    runtime: str | None = None,
    params: dict | None = None,
) -> str:
    if not script_source or len(script_source.encode("utf-8")) > MAX_SCRIPT_BYTES:
        raise manager.AdbError("script source is empty or too large")
    if runtime is not None:
        runtime = str(runtime).strip().lower() or None
    if runtime is not None and runtime not in _VALID_RUNTIMES:
        raise manager.AdbError(f"invalid runtime '{runtime}' (expected qjs or v8)")
    script_source = inject_script_params(script_source, params)
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
    create_kwargs = {}
    if runtime:
        create_kwargs["runtime"] = runtime
    try:
        script = session.create_script(script_source, **create_kwargs)
    except TypeError:
        # Older frida bindings without runtime kwarg.
        if create_kwargs:
            raise manager.AdbError("this frida build does not support runtime selection") from None
        script = session.create_script(script_source)
    messages: queue.Queue = queue.Queue()

    def on_message(message, data):
        messages.put({"message": message, "data": data.decode("utf-8", errors="replace") if data else None})

    def on_log(level: str, text: str):
        # Structured console routing (info/warning/error) instead of opaque message events.
        messages.put({"message": {"type": "log", "level": str(level or "info"), "payload": text}, "data": None})

    script.on("message", on_message)
    try:
        script.set_log_handler(on_log)
    except Exception:
        pass  # older bindings; logs still arrive as type=log messages if supported
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
            "runtime": runtime,
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


_EXPORT_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _json_safe(value):
    """Make an rpc.exports return value JSON-serializable.

    Frida can hand back bytes (e.g. Memory.readByteArray results); represent
    those as a hex string rather than letting jsonify choke on them.
    """
    if isinstance(value, (bytes, bytearray)):
        return {"__bytes_hex__": bytes(value).hex()}
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _live_session(session_id: str) -> dict:
    with _sessions_lock:
        entry = _sessions.get(session_id)
        if not entry:
            raise manager.AdbError("session not found")
        _refresh_detach_state(entry)
        if entry.get("detached"):
            raise manager.AdbError("session is detached")
        return entry


def list_script_exports(session_id: str) -> list[str]:
    """List the rpc.exports functions a session's script defines (snake_case)."""
    entry = _live_session(session_id)
    try:
        return sorted(str(name) for name in entry["script"].list_exports())
    except Exception as exc:
        raise manager.AdbError(f"failed to list exports: {exc}") from exc


def call_script_export(session_id: str, name: str, args: list | None = None):
    """Invoke an rpc.exports function by name with positional JSON args."""
    name = str(name or "").strip()
    if not _EXPORT_NAME_RE.match(name):
        raise manager.AdbError("invalid export name")
    if args is None:
        args = []
    if not isinstance(args, list):
        raise manager.AdbError("export args must be a JSON array")
    entry = _live_session(session_id)
    try:
        available = set(entry["script"].list_exports())
    except Exception as exc:
        raise manager.AdbError(f"failed to list exports: {exc}") from exc
    if name not in available:
        raise manager.AdbError(f"export '{name}' not found")
    fn = getattr(entry["script"].exports, name, None)
    if fn is None:
        raise manager.AdbError(f"export '{name}' not callable")
    try:
        result = fn(*args)
    except Exception as exc:
        raise manager.AdbError(f"export call failed: {exc}") from exc
    return _json_safe(result)


def post_message(session_id: str, message, data: str | None = None) -> dict:
    """Send a message into a live script (the agent receives it via recv()).

    `message` is any JSON-serializable value; optional `data` is a hex string
    delivered as the binary side-channel of script.post().
    """
    entry = _live_session(session_id)
    binary = None
    if data is not None:
        try:
            binary = bytes.fromhex(str(data))
        except ValueError as exc:
            raise manager.AdbError("data must be a hex string") from exc
    try:
        entry["script"].post(message, data=binary)
    except Exception as exc:
        raise manager.AdbError(f"post failed: {exc}") from exc
    return {"ok": True}


def set_child_gating(session_id: str, enable: bool) -> dict:
    """Enable/disable following fork()/exec() children on a live session.

    Child gating suspends spawned children so they can be inspected before they
    run; enumerate pending children on the device and resume/kill them by pid.
    """
    entry = _live_session(session_id)
    session = entry["session"]
    try:
        if enable:
            session.enable_child_gating()
        else:
            session.disable_child_gating()
    except Exception as exc:
        verb = "enable" if enable else "disable"
        raise manager.AdbError(f"failed to {verb} child gating: {exc}") from exc
    entry["child_gating"] = bool(enable)
    return {"ok": True, "child_gating": bool(enable)}


def eternalize_session(session_id: str) -> dict:
    """Keep the agent running after this client disconnects (fire-and-forget).

    Calls script.eternalize(), then detaches the client session without unloading
    the script so hooks remain active on the target.
    """
    entry = _live_session(session_id)
    try:
        entry["script"].eternalize()
    except Exception as exc:
        raise manager.AdbError(f"eternalize failed: {exc}") from exc
    with _sessions_lock:
        entry = _sessions.pop(session_id, None)
    if entry:
        try:
            entry["session"].detach()
        except Exception:
            pass
    return {"ok": True, "eternalized": True}


def interrupt_script(session_id: str) -> dict:
    """Interrupt a busy script's current execution (it can continue afterwards)."""
    entry = _live_session(session_id)
    try:
        entry["script"].interrupt()
    except Exception as exc:
        raise manager.AdbError(f"interrupt failed: {exc}") from exc
    return {"ok": True, "interrupted": True}


def terminate_script(session_id: str) -> dict:
    """Force-terminate a runaway script and drop the session.

    Unlike detach() (which unloads cleanly), terminate() is the hard stop for a
    script that will not yield; afterwards the session is removed and detached.
    """
    entry = _live_session(session_id)
    try:
        entry["script"].terminate()
    except Exception as exc:
        raise manager.AdbError(f"terminate failed: {exc}") from exc
    with _sessions_lock:
        entry = _sessions.pop(session_id, None)
    if entry:
        try:
            entry["session"].detach()
        except Exception:
            pass
    return {"ok": True, "terminated": True}


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
