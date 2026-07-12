"""Frida server provisioning, script storage, and live session registry."""
from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import lzma
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path

import requests

import config
from . import devices, manager, process_manager

FRIDA_SERVER_REMOTE = "/data/local/tmp/frida-server"
FRIDA_PID_REMOTE = "/data/local/tmp/frida-server.pid"
MAC_LOCAL_SERIAL = "mac-local"
MAX_SCRIPT_BYTES = 256 * 1024
FRIDA_PIP_PACKAGES = ("frida", "frida-tools")
FRIDA_CLI_TOOLS = ("frida", "frida-ps", "frida-trace", "frida-ls-devices")
_MAX_SESSION_LOG = 5000
_MAX_DEVICE_EVENT_LOG = 500
_VALID_STDIO = frozenset({"inherit", "pipe"})

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
# Keep device objects alive so signal handlers stay wired, and buffer device events.
_device_refs: dict[str, object] = {}
_device_events: dict[str, deque] = {}
_device_events_lock = threading.Lock()
_wired_serials: set[str] = set()


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


def _mac_frida_device():
    if platform.system() != "Darwin":
        raise manager.AdbError("macOS host instrumentation is only available on macOS")
    frida = _import_frida()
    if not frida:
        raise manager.AdbError("frida package not installed")
    try:
        return frida.get_local_device()
    except Exception as exc:
        raise manager.AdbError(f"failed to get local Frida device: {exc}") from exc


def _device_public(device) -> dict:
    return {
        "id": getattr(device, "id", None),
        "name": getattr(device, "name", None),
        "type": getattr(device, "type", None),
    }


def get_mac_status() -> dict:
    """Return host macOS Frida availability without touching Android/ADB."""
    version = _frida_version()
    result = {
        "ok": True,
        "platform": platform.system(),
        "python_installed": bool(version),
        "python_version": version,
        "available": False,
        "device": None,
    }
    if platform.system() != "Darwin":
        result["error"] = "macOS host instrumentation is only available on macOS"
        return result
    if not version:
        result["error"] = "frida package not installed"
        return result
    try:
        device = _mac_frida_device()
        result["available"] = True
        result["device"] = _device_public(device)
    except manager.AdbError as exc:
        result["error"] = str(exc)
    return result


def _require_macos_tools_host() -> None:
    if platform.system() != "Darwin":
        raise manager.AdbError("Frida host tools can only be managed from macOS")


def _package_status(distribution: str) -> dict:
    try:
        version = importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        version = None
    return {
        "installed": version is not None,
        "version": version,
    }


def _cli_status(name: str) -> dict:
    path = shutil.which(name)
    result = {"installed": bool(path), "path": path, "version": None, "error": None}
    if not path:
        return result
    try:
        proc = subprocess.run(
            [path, "--version"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        output = (proc.stdout or proc.stderr or "").strip().splitlines()
        result["version"] = output[0].strip() if output else None
        if proc.returncode != 0:
            result["error"] = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["error"] = str(exc)
    return result


def get_mac_tools_status() -> dict:
    """Return macOS Frida Python package + CLI tool availability."""
    packages = {name: _package_status(name) for name in FRIDA_PIP_PACKAGES}
    cli = {name: _cli_status(name) for name in FRIDA_CLI_TOOLS}
    python_api = get_mac_status()
    installed = bool(packages["frida"]["installed"] and packages["frida-tools"]["installed"])
    cli_ready = all(tool["installed"] for tool in cli.values())
    return {
        "ok": True,
        "platform": platform.system(),
        "is_macos": platform.system() == "Darwin",
        "python": sys.executable,
        "pip_command": [sys.executable, "-m", "pip", "install", "--upgrade", *FRIDA_PIP_PACKAGES],
        "packages": packages,
        "cli": cli,
        "python_api": python_api,
        "installed": installed,
        "cli_ready": cli_ready,
        "needs_install": not installed,
        "needs_update": False,
        "can_install": platform.system() == "Darwin",
    }


def _trim_command_output(value: str, limit: int = 6000) -> str:
    value = value or ""
    if len(value) <= limit:
        return value
    return value[-limit:]


def install_or_update_mac_tools(update: bool = False) -> dict:
    """Install or update Frida host tooling into the running Python environment."""
    _require_macos_tools_host()
    cmd = [sys.executable, "-m", "pip", "install"]
    if update:
        cmd.append("--upgrade")
    cmd.extend(FRIDA_PIP_PACKAGES)
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise manager.AdbError(f"pip {'update' if update else 'install'} timed out after {exc.timeout}s") from exc
    except OSError as exc:
        raise manager.AdbError(f"failed to run pip: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
        raise manager.AdbError(f"pip {'update' if update else 'install'} failed: {detail}")
    return {
        "ok": True,
        "action": "update" if update else "install",
        "command": cmd,
        "stdout": _trim_command_output(proc.stdout),
        "stderr": _trim_command_output(proc.stderr),
        "status": get_mac_tools_status(),
    }


def test_mac_tools() -> dict:
    """Exercise the local Frida Python API and any installed CLI tools."""
    _require_macos_tools_host()
    checks = {}
    try:
        device = _mac_frida_device()
        checks["python_api"] = {
            "ok": True,
            "device": _device_public(device),
            "system": _json_safe(dict(device.query_system_parameters() or {})),
            "process_count": len(device.enumerate_processes()),
        }
    except Exception as exc:
        checks["python_api"] = {"ok": False, "error": str(exc)}

    frida_cli = shutil.which("frida")
    if frida_cli:
        try:
            proc = subprocess.run(
                [frida_cli, "--version"],
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
            checks["frida_cli"] = {
                "ok": proc.returncode == 0,
                "version": (proc.stdout or proc.stderr or "").strip().splitlines()[0]
                if (proc.stdout or proc.stderr or "").strip() else None,
                "stderr": _trim_command_output(proc.stderr, 1000),
            }
        except (OSError, subprocess.TimeoutExpired) as exc:
            checks["frida_cli"] = {"ok": False, "error": str(exc)}
    else:
        checks["frida_cli"] = {"ok": False, "error": "frida CLI not found on PATH"}

    ok = all(bool(check.get("ok")) for check in checks.values())
    return {"ok": ok, "checks": checks, "status": get_mac_tools_status()}


def _enumerate_processes_with_metadata(device):
    try:
        return device.enumerate_processes(scope="metadata")
    except TypeError:
        return device.enumerate_processes()


def _process_public(proc, include_parameters: bool = False) -> dict:
    out = {"pid": proc.pid, "name": proc.name}
    if include_parameters:
        out["parameters"] = _json_safe(dict(getattr(proc, "parameters", None) or {}))
    return out


def list_processes(serial: str) -> list[dict]:
    try:
        device = _frida_device(serial)
        return sorted(
            [_process_public(p) for p in device.enumerate_processes()],
            key=lambda p: (str(p["name"]).lower(), p["pid"]),
        )
    except Exception:
        return process_manager.list_processes(serial).get("processes", [])


def list_mac_processes() -> list[dict]:
    device = _mac_frida_device()
    try:
        processes = _enumerate_processes_with_metadata(device)
    except Exception as exc:
        raise manager.AdbError(f"failed to enumerate macOS processes: {exc}") from exc
    return sorted(
        (_process_public(proc, include_parameters=True) for proc in processes),
        key=lambda p: (str(p["name"]).lower(), p["pid"]),
    )


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


def list_mac_applications() -> list[dict]:
    device = _mac_frida_device()
    try:
        apps = device.enumerate_applications()
    except Exception as exc:
        raise manager.AdbError(f"failed to enumerate macOS applications: {exc}") from exc
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


def get_mac_frontmost_application() -> dict | None:
    device = _mac_frida_device()
    try:
        app = device.get_frontmost_application()
    except Exception as exc:
        raise manager.AdbError(f"failed to query macOS frontmost application: {exc}") from exc
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
    wire_device_events(serial, device=device)
    return {"ok": True, "spawn_gating": True}


def enable_mac_spawn_gating() -> dict:
    device = _mac_frida_device()
    try:
        device.enable_spawn_gating()
    except Exception as exc:
        raise manager.AdbError(f"failed to enable macOS spawn gating: {exc}") from exc
    wire_device_events(MAC_LOCAL_SERIAL, device=device)
    return {"ok": True, "spawn_gating": True}


def disable_spawn_gating(serial: str) -> dict:
    device = _frida_device(serial)
    try:
        device.disable_spawn_gating()
    except Exception as exc:
        raise manager.AdbError(f"failed to disable spawn gating: {exc}") from exc
    return {"ok": True, "spawn_gating": False}


def disable_mac_spawn_gating() -> dict:
    device = _mac_frida_device()
    try:
        device.disable_spawn_gating()
    except Exception as exc:
        raise manager.AdbError(f"failed to disable macOS spawn gating: {exc}") from exc
    return {"ok": True, "spawn_gating": False}


def _spawn_public(spawn) -> dict:
    return {
        "pid": getattr(spawn, "pid", None),
        "identifier": getattr(spawn, "identifier", None),
    }


def _child_public(child) -> dict:
    return {
        "pid": getattr(child, "pid", None),
        "parent_pid": getattr(child, "parent_pid", None),
        "identifier": getattr(child, "identifier", None),
        "path": getattr(child, "path", None),
    }


def _crash_public(crash) -> dict:
    return {
        "pid": getattr(crash, "pid", None),
        "process_name": getattr(crash, "process_name", None),
        "summary": getattr(crash, "summary", None),
        "report": getattr(crash, "report", None),
    }


def _append_device_event(serial: str, event: dict) -> None:
    """Record a device-level event and fan it out to live sessions on this serial."""
    entry = {**event, "ts": time.time()}
    with _device_events_lock:
        buf = _device_events.setdefault(serial, deque(maxlen=_MAX_DEVICE_EVENT_LOG))
        buf.append(entry)
    with _sessions_lock:
        for sess in _sessions.values():
            if sess.get("serial") != serial or sess.get("detached"):
                continue
            try:
                payload = {"message": entry, "data": None}
                sess["queue"].put_nowait(payload)
                log = sess.get("log")
                if log is not None:
                    log.append(payload)
                    if len(log) > _MAX_SESSION_LOG:
                        del log[: len(log) - _MAX_SESSION_LOG]
            except Exception:
                pass


def wire_device_events(serial: str, device=None) -> dict:
    """Subscribe to spawn/child/crash/output signals (idempotent per serial).

    Events are buffered for polling and also pushed into live session consoles
    for the same device serial.
    """
    if serial in _wired_serials:
        return {"ok": True, "wired": True, "already": True}
    if device is None:
        device = _frida_device(serial)
    _device_refs[serial] = device  # keep alive for signal handlers

    def on_spawn_added(spawn):
        _append_device_event(serial, {"type": "spawn-added", **_spawn_public(spawn)})

    def on_spawn_removed(spawn):
        _append_device_event(serial, {"type": "spawn-removed", **_spawn_public(spawn)})

    def on_child_added(child):
        _append_device_event(serial, {"type": "child-added", **_child_public(child)})

    def on_child_removed(child):
        _append_device_event(serial, {"type": "child-removed", **_child_public(child)})

    def on_process_crashed(crash):
        _append_device_event(serial, {"type": "process-crashed", **_crash_public(crash)})

    def on_output(pid, fd, data):
        text = data.decode("utf-8", errors="replace") if isinstance(data, (bytes, bytearray)) else str(data)
        _append_device_event(serial, {
            "type": "output",
            "pid": pid,
            "fd": fd,
            "data": text,
        })

    for signal, handler in (
        ("spawn-added", on_spawn_added),
        ("spawn-removed", on_spawn_removed),
        ("child-added", on_child_added),
        ("child-removed", on_child_removed),
        ("process-crashed", on_process_crashed),
        ("output", on_output),
    ):
        try:
            device.on(signal, handler)
        except Exception:
            pass  # best-effort; some signals may be unavailable
    _wired_serials.add(serial)
    return {"ok": True, "wired": True, "already": False}


def wire_mac_device_events() -> dict:
    if MAC_LOCAL_SERIAL in _wired_serials:
        return wire_device_events(MAC_LOCAL_SERIAL)
    device = _mac_frida_device()
    return wire_device_events(MAC_LOCAL_SERIAL, device=device)


def list_device_events(serial: str, after_ts: float | None = None, limit: int = 100) -> list[dict]:
    """Return recent device events (spawn/child/crash/output), newest last.

    If after_ts is set, only events with ts > after_ts are returned.
    """
    try:
        limit = max(1, min(int(limit), _MAX_DEVICE_EVENT_LOG))
    except (TypeError, ValueError):
        limit = 100
    wire_device_events(serial)
    with _device_events_lock:
        events = list(_device_events.get(serial, ()))
    if after_ts is not None:
        try:
            after = float(after_ts)
        except (TypeError, ValueError):
            after = None
        if after is not None:
            events = [e for e in events if (e.get("ts") or 0) > after]
    return events[-limit:]


def list_mac_device_events(after_ts: float | None = None, limit: int = 100) -> list[dict]:
    try:
        limit = max(1, min(int(limit), _MAX_DEVICE_EVENT_LOG))
    except (TypeError, ValueError):
        limit = 100
    wire_mac_device_events()
    with _device_events_lock:
        events = list(_device_events.get(MAC_LOCAL_SERIAL, ()))
    if after_ts is not None:
        try:
            after = float(after_ts)
        except (TypeError, ValueError):
            after = None
        if after is not None:
            events = [e for e in events if (e.get("ts") or 0) > after]
    return events[-limit:]


def input_to_process(serial: str, pid, data) -> dict:
    """Feed bytes to a spawned process's stdin via device.input(pid, data).

    `data` may be bytes, a UTF-8 string, or a hex string when encoding='hex' is
    used by the caller (routes decode before calling).
    """
    device = _frida_device(serial)
    value = _require_pid(pid)
    if isinstance(data, str):
        raw = data.encode("utf-8")
    elif isinstance(data, (bytes, bytearray)):
        raw = bytes(data)
    else:
        raise manager.AdbError("input data must be a string or bytes")
    if not raw:
        raise manager.AdbError("input data is empty")
    if len(raw) > 64 * 1024:
        raise manager.AdbError("input data is too large (max 64 KiB)")
    try:
        device.input(value, raw)
    except Exception as exc:
        raise manager.AdbError(f"failed to send input to pid {value}: {exc}") from exc
    return {"ok": True, "pid": value, "bytes": len(raw)}


def input_to_mac_process(pid, data) -> dict:
    device = _mac_frida_device()
    value = _require_pid(pid)
    if isinstance(data, str):
        raw = data.encode("utf-8")
    elif isinstance(data, (bytes, bytearray)):
        raw = bytes(data)
    else:
        raise manager.AdbError("input data must be a string or bytes")
    if not raw:
        raise manager.AdbError("input data is empty")
    if len(raw) > 64 * 1024:
        raise manager.AdbError("input data is too large (max 64 KiB)")
    try:
        device.input(value, raw)
    except Exception as exc:
        raise manager.AdbError(f"failed to send input to macOS pid {value}: {exc}") from exc
    return {"ok": True, "pid": value, "bytes": len(raw)}


def _normalize_spawn_target(target: dict) -> dict:
    """Validate optional spawn kwargs (argv/env/cwd/stdio) on a spawn target dict."""
    out = dict(target)
    if "argv" in out and out["argv"] is not None:
        if not isinstance(out["argv"], (list, tuple)):
            raise manager.AdbError("argv must be a list of strings")
        out["argv"] = [str(a) for a in out["argv"]]
    envp = out.get("envp") if out.get("envp") is not None else out.get("env")
    if envp is not None:
        if not isinstance(envp, dict):
            raise manager.AdbError("env/envp must be an object of string values")
        out["envp"] = {str(k): str(v) for k, v in envp.items()}
        out.pop("env", None)
    if out.get("cwd") is not None:
        out["cwd"] = str(out["cwd"])
    if out.get("stdio") is not None:
        stdio = str(out["stdio"]).strip().lower()
        if stdio not in _VALID_STDIO:
            raise manager.AdbError("stdio must be 'inherit' or 'pipe'")
        out["stdio"] = stdio
    return out


def _spawn_process(device, target: dict) -> int:
    """Spawn a program with optional argv/envp/cwd/stdio from the target dict."""
    program = str(target["spawn"])
    kwargs = {}
    if target.get("argv") is not None:
        kwargs["argv"] = target["argv"]
    if target.get("envp") is not None:
        kwargs["envp"] = target["envp"]
    if target.get("cwd") is not None:
        kwargs["cwd"] = target["cwd"]
    if target.get("stdio") is not None:
        kwargs["stdio"] = target["stdio"]
    try:
        if kwargs:
            return int(device.spawn(program, **kwargs))
        return int(device.spawn([program]))
    except TypeError:
        # Older bindings: list form only (program + optional argv tail).
        if kwargs.get("argv"):
            return int(device.spawn([program, *kwargs["argv"]]))
        return int(device.spawn([program]))
    except manager.AdbError:
        raise
    except Exception as exc:
        raise manager.AdbError(f"spawn failed: {exc}") from exc


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


def list_mac_pending_spawn() -> list[dict]:
    device = _mac_frida_device()
    try:
        pending = device.enumerate_pending_spawn()
    except Exception as exc:
        raise manager.AdbError(f"failed to list macOS pending spawn: {exc}") from exc
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


def list_mac_pending_children() -> list[dict]:
    device = _mac_frida_device()
    try:
        pending = device.enumerate_pending_children()
    except Exception as exc:
        raise manager.AdbError(f"failed to list macOS pending children: {exc}") from exc
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


def resume_mac_pid(pid) -> dict:
    device = _mac_frida_device()
    value = _require_pid(pid)
    try:
        device.resume(value)
    except Exception as exc:
        raise manager.AdbError(f"failed to resume macOS pid {value}: {exc}") from exc
    return {"ok": True, "pid": value, "resumed": True}


def kill_pid(serial: str, pid) -> dict:
    """Kill a process by PID on the device via the Frida device API."""
    return kill_process(serial, pid)


def kill_process(serial: str, target) -> dict:
    """Kill a process by PID or name via device.kill().

    Numeric strings are treated as PIDs; anything else is a process name.
    """
    device = _frida_device(serial)
    raw = str(target if target is not None else "").strip()
    if not raw:
        raise manager.AdbError("missing kill target (pid or name)")
    if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
        value = _require_pid(raw)
        key = "pid"
    else:
        value = raw
        key = "name"
    try:
        device.kill(value)
    except Exception as exc:
        raise manager.AdbError(f"failed to kill {key} {value}: {exc}") from exc
    result = {"ok": True, "killed": True, key: value}
    return result


def kill_mac_process(target) -> dict:
    device = _mac_frida_device()
    raw = str(target if target is not None else "").strip()
    if not raw:
        raise manager.AdbError("missing kill target (pid or name)")
    if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
        value = _require_pid(raw)
        key = "pid"
    else:
        value = raw
        key = "name"
    try:
        device.kill(value)
    except Exception as exc:
        raise manager.AdbError(f"failed to kill macOS {key} {value}: {exc}") from exc
    return {"ok": True, "killed": True, key: value}


def get_system_parameters(serial: str) -> dict:
    """Return the device details Frida reports (os, arch, platform, access, name)."""
    device = _frida_device(serial)
    try:
        params = device.query_system_parameters()
    except Exception as exc:
        raise manager.AdbError(f"failed to query system parameters: {exc}") from exc
    return _json_safe(dict(params or {}))


def get_mac_system_parameters() -> dict:
    device = _mac_frida_device()
    try:
        params = device.query_system_parameters()
    except Exception as exc:
        raise manager.AdbError(f"failed to query macOS system parameters: {exc}") from exc
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


def get_mac_process(query) -> dict:
    device = _mac_frida_device()
    q = str(query or "").strip()
    if not q:
        raise manager.AdbError("missing process name or pid")
    try:
        if q.isdigit():
            pid = int(q)
            procs = _enumerate_processes_with_metadata(device)
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
        raise manager.AdbError(f"macOS process lookup failed: {exc}") from exc
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
        "report": getattr(crash, "report", None),
    }


def _append_session_log(message_log: list | None, item: dict) -> None:
    if message_log is None:
        return
    message_log.append(item)
    if len(message_log) > _MAX_SESSION_LOG:
        del message_log[: len(message_log) - _MAX_SESSION_LOG]


def _make_detach_handler(session_id: str, messages: "queue.Queue", message_log: list | None = None):
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
        item = {"message": payload, "data": None}
        messages.put(item)
        _append_session_log(message_log, item)
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


def _normalize_attach_inputs(script_source: str, runtime: str | None, params: dict | None) -> tuple[str, str | None]:
    if not script_source or len(script_source.encode("utf-8")) > MAX_SCRIPT_BYTES:
        raise manager.AdbError("script source is empty or too large")
    if runtime is not None:
        runtime = str(runtime).strip().lower() or None
    if runtime is not None and runtime not in _VALID_RUNTIMES:
        raise manager.AdbError(f"invalid runtime '{runtime}' (expected qjs or v8)")
    return inject_script_params(script_source, params), runtime


def attach(
    serial: str,
    target,
    script_source: str,
    runtime: str | None = None,
    params: dict | None = None,
) -> str:
    script_source, runtime = _normalize_attach_inputs(script_source, runtime, params)
    check_version_compatibility(serial)
    device = _frida_device(serial)
    return _attach_to_device(serial, device, target, script_source, runtime)


def attach_mac(
    target,
    script_source: str,
    runtime: str | None = None,
    params: dict | None = None,
) -> str:
    script_source, runtime = _normalize_attach_inputs(script_source, runtime, params)
    device = _mac_frida_device()
    return _attach_to_device(MAC_LOCAL_SERIAL, device, target, script_source, runtime)


def _attach_to_device(
    serial: str,
    device,
    target,
    script_source: str,
    runtime: str | None = None,
) -> str:
    wire_device_events(serial, device=device)
    spawned_pid = None
    if isinstance(target, dict):
        if target.get("spawn"):
            target = _normalize_spawn_target(target)
            spawned_pid = _spawn_process(device, target)
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
    message_log: list = []

    def on_message(message, data):
        item = {
            "message": message,
            "data": data.decode("utf-8", errors="replace") if data else None,
        }
        if isinstance(data, (bytes, bytearray)) and data:
            item["data_hex"] = bytes(data).hex()
        messages.put(item)
        _append_session_log(message_log, item)

    def on_log(level: str, text: str):
        # Structured console routing (info/warning/error) instead of opaque message events.
        item = {"message": {"type": "log", "level": str(level or "info"), "payload": text}, "data": None}
        messages.put(item)
        _append_session_log(message_log, item)

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
            "log": message_log,
            "created_at": time.time(),
            "detached": False,
            "detach_reason": None,
            "runtime": runtime,
            "spawned_pid": spawned_pid,
        }
    try:
        session.on("detached", _make_detach_handler(session_id, messages, message_log))
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
    if enable and entry.get("serial"):
        wire_device_events(entry["serial"])
    return {"ok": True, "child_gating": bool(enable)}


def export_session_messages(session_id: str, fmt: str = "json"):
    """Export the buffered session message log as JSON (dict) or plain text.

    Messages are accumulated from script output, logs, detach events, and
    device-level events fan-out while the session is live. Detached sessions
    still export until the session is dropped from the registry.
    """
    fmt = (fmt or "json").strip().lower()
    if fmt not in ("json", "text"):
        raise manager.AdbError("format must be 'json' or 'text'")
    with _sessions_lock:
        entry = _sessions.get(session_id)
        if not entry:
            raise manager.AdbError("session not found")
        log = list(entry.get("log") or [])
        meta = {
            "session_id": session_id,
            "serial": entry.get("serial"),
            "target": entry.get("target"),
            "detached": entry.get("detached", False),
            "detach_reason": entry.get("detach_reason"),
            "runtime": entry.get("runtime"),
            "count": len(log),
        }
    if fmt == "text":
        lines = []
        for item in log:
            msg = item.get("message") or {}
            data = item.get("data")
            mtype = msg.get("type") or "message"
            if mtype == "log":
                lines.append(f"{msg.get('level') or 'info'}: {msg.get('payload') if msg.get('payload') is not None else ''}")
            elif mtype == "send":
                lines.append(f"send: {json.dumps(msg.get('payload'), ensure_ascii=False, default=str)}")
            elif mtype == "error":
                lines.append(f"error: {msg.get('description') or json.dumps(msg, ensure_ascii=False, default=str)}")
            elif mtype == "detached":
                lines.append(f"detached: {msg.get('reason') or 'unknown'}")
            elif mtype == "process-crashed":
                lines.append(
                    f"crash: pid={msg.get('pid')} {msg.get('process_name') or ''} — {msg.get('summary') or ''}".strip()
                )
            elif mtype == "output":
                lines.append(f"stdout/err[{msg.get('fd')}] pid={msg.get('pid')}: {msg.get('data') or ''}")
            elif mtype in ("spawn-added", "spawn-removed", "child-added", "child-removed"):
                lines.append(f"{mtype}: pid={msg.get('pid')} {msg.get('identifier') or msg.get('path') or ''}".strip())
            else:
                lines.append(f"{mtype}: {json.dumps(msg, ensure_ascii=False, default=str)}")
            if data and mtype not in ("output",):
                lines.append(f"  data: {data}")
            if item.get("data_hex"):
                lines.append(f"  data_hex: {item['data_hex']}")
        return {"ok": True, "format": "text", "text": "\n".join(lines), **meta}
    return {"ok": True, "format": "json", "messages": _json_safe(log), **meta}


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
