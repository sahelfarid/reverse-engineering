"""SSL/TLS pinning detection and Frida-based bypass.

Detection is purely observational, static (JADX source/resource pattern
scan, same shape as adb/root_checker.py) and dynamic (a short spawn+observe
Frida window via the drain_messages() helper) -- nothing about how the app
behaves is changed by a detect call.

Bypass is a deliberately separate, heavier action: it attaches a
persistent Frida session (through adb.frida_manager, so it shows up in the
same session registry as any other attach -- /api/frida/sessions,
.../stream, .../detach all work on it) that actually installs a permissive
TrustManager and no-ops known pinning checks. That's a real behavior change,
so callers must pass `confirm: true` and every bypass attach is audit-logged
with the script's hash -- "requires explicit authorization" as code, not
just a comment.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import config
from . import frida_manager, jadx_manager, manager, packages

_MAX_SCANNED_FILES = 20_000
_MAX_FILE_BYTES = 2 * 1024 * 1024

_JAVA_PATTERNS: list[tuple[str, str, "re.Pattern"]] = [
    ("okhttp-certificate-pinner", "high", re.compile(r"CertificatePinner")),
    ("custom-trust-manager", "high", re.compile(r"implements\s+(?:[\w.]*\.)?X509TrustManager\b|class\s+\w*TrustManager\b")),
    ("custom-hostname-verifier", "medium", re.compile(r"implements\s+(?:[\w.]*\.)?HostnameVerifier\b|class\s+\w*HostnameVerifier\b")),
    ("trustkit-library", "high", re.compile(r"com\.datatheorem\.android\.trustkit")),
    ("network-security-config-ref", "medium", re.compile(r"networkSecurityConfig")),
    ("ssl-pin-digest-literal", "high", re.compile(r'"sha256/[A-Za-z0-9+/=]{20,}"')),
    ("conscrypt-reference", "low", re.compile(r"org\.conscrypt")),
]


def _java_findings(root: Path) -> list[dict]:
    findings = []
    scanned = 0
    for path in root.rglob("*.java"):
        if scanned >= _MAX_SCANNED_FILES:
            break
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        rel = str(path.relative_to(root))
        for lineno, line in enumerate(text.splitlines(), start=1):
            for finding_id, severity, pattern in _JAVA_PATTERNS:
                if pattern.search(line):
                    findings.append({
                        "id": finding_id, "severity": severity, "file": rel, "line": lineno,
                        "snippet": line.strip()[:300],
                    })
    return findings


def _xml_findings(root: Path) -> list[dict]:
    """Network Security Config pin-sets survive jadx's resource decompile as
    plain XML under res/xml/ -- catch them the same way manifest_summary()
    reads the already-decompiled AndroidManifest.xml."""
    findings = []
    scanned = 0
    for path in root.rglob("*.xml"):
        if scanned >= _MAX_SCANNED_FILES:
            break
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        if "<pin-set" in text or re.search(r"<pin\s+digest=", text):
            findings.append({
                "id": "network-security-config-pin-set", "severity": "high",
                "file": str(path.relative_to(root)), "line": None,
                "snippet": "<pin-set> found in network security config",
            })
    return findings


def static_scan(package: str) -> dict:
    root = jadx_manager.project_dir(package)
    if not root.is_dir():
        return {"available": False, "reason": "no JADX project decompiled for this package yet", "findings": []}
    findings = _java_findings(root) + _xml_findings(root)
    return {"available": True, "findings": findings}


# Observational only: reports which pinning mechanism fired, changes nothing.
DETECT_OBSERVER_SCRIPT = r"""
Java.perform(function () {
  function hit(check, detail) {
    send({ type: "pinning_check_hit", check: check, detail: String(detail) });
  }

  try {
    var CertificatePinner = Java.use("okhttp3.CertificatePinner");
    CertificatePinner.check.overloads.forEach(function (ov) {
      ov.implementation = function () {
        hit("okhttp_certificate_pinner_check", arguments[0]);
        return ov.apply(this, arguments);
      };
    });
  } catch (e) {}

  try {
    Java.use("com.datatheorem.android.trustkit.TrustKit");
    hit("trustkit_present", "com.datatheorem.android.trustkit.TrustKit resolved");
  } catch (e) {}

  try {
    Java.enumerateLoadedClassesSync().forEach(function (name) {
      if (name.indexOf("TrustManager") === -1) return;
      if (name.indexOf("com.android.org.conscrypt") === 0 || name.indexOf("javax.net.ssl") === 0) return;
      try {
        var Cls = Java.use(name);
        if (!Cls.checkServerTrusted) return;
        Cls.checkServerTrusted.overloads.forEach(function (ov) {
          ov.implementation = function () {
            hit("custom_trust_manager_check", name);
            return ov.apply(this, arguments);
          };
        });
      } catch (e) {}
    });
  } catch (e) {}

  send({ type: "notice", message: "ssl-pinning detection observer attached" });
});
"""


def observe_dynamic(serial: str, package: str, duration_sec: float = 4.0) -> dict:
    try:
        session_id = frida_manager.attach(serial, {"spawn": package}, DETECT_OBSERVER_SCRIPT)
    except manager.AdbError as exc:
        return {"available": False, "reason": str(exc), "events": []}

    try:
        raw = frida_manager.drain_messages(session_id, duration_sec)
    finally:
        frida_manager.detach(session_id)

    events = []
    for item in raw:
        payload = (item.get("message") or {}).get("payload")
        if isinstance(payload, dict) and payload.get("type") == "pinning_check_hit":
            events.append({"check": payload.get("check"), "detail": payload.get("detail")})
    return {"available": True, "events": events}


def summarize(static_result: dict, dynamic_result: dict) -> dict:
    matched: list[str] = []
    for f in static_result.get("findings", []):
        matched.append(f"static: {f['id']} ({f['file']}:{f['line']})")
    for e in dynamic_result.get("events", []):
        matched.append(f"dynamic: {e['check']} ({e['detail']})")

    has_static = bool(static_result.get("findings"))
    has_dynamic = bool(dynamic_result.get("events"))
    if has_static and has_dynamic:
        verdict = "SSL/TLS pinning implemented (static + dynamic evidence)"
    elif has_static or has_dynamic:
        verdict = "SSL/TLS pinning likely implemented"
    else:
        verdict = "no SSL/TLS pinning evidence found"

    return {"verdict": verdict, "matched_indicators": matched}


def get_detection_report(
    serial: str, package: str, *, run_dynamic: bool = True, dynamic_duration_sec: float = 4.0,
) -> dict:
    manager.validate_serial(serial)
    packages.validate_package(package)

    static_result = static_scan(package)
    if run_dynamic:
        dynamic_result = observe_dynamic(serial, package, dynamic_duration_sec)
    else:
        dynamic_result = {"available": False, "reason": "dynamic check skipped", "events": []}

    summary = summarize(static_result, dynamic_result)
    return {
        **summary,
        "package": package,
        "static": static_result,
        "dynamic": dynamic_result,
        "checked_at": int(time.time()),
        "disclaimer": (
            "Best-effort evidence from static source/resource patterns and a short dynamic "
            "observation window. Absence of matches does not prove the app has no pinning -- "
            "obfuscated, native, or custom pinning may not match these patterns or trigger "
            "during the observed window."
        ),
    }


# --- bypass script store -----------------------------------------------------
# Separate store from adb/frida_manager.py's general script store (different
# subdirectory, different default set) since these are a distinct, more
# sensitive category -- but reuses its name validation and hashing rather
# than re-implementing them.

BYPASS_SCRIPTS: dict[str, dict] = {
    "universal-trust-manager-bypass": {
        "readonly": True,
        "description": (
            "Authorized testing only: installs a permissive X509TrustManager via SSLContext.init "
            "and no-ops OkHttp's CertificatePinner.check and HttpsURLConnection hostname-verifier "
            "setters, so a proxy's certificate is accepted for traffic inspection on your own app."
        ),
        "source": r"""// Authorized testing only: use against your own app / lab traffic.
Java.perform(function () {
  function log(msg) { send({ type: "bypass_event", message: msg }); }

  try {
    var X509TrustManager = Java.use("javax.net.ssl.X509TrustManager");
    var SSLContext = Java.use("javax.net.ssl.SSLContext");

    var TrustAll = Java.registerClass({
      name: "com.adbpanel.sslbypass.TrustAll",
      implements: [X509TrustManager],
      methods: {
        checkClientTrusted: function () {},
        checkServerTrusted: function () {},
        getAcceptedIssuers: function () { return []; },
      },
    });
    var trustManagers = [TrustAll.$new()];

    var init = SSLContext.init.overload(
      "[Ljavax.net.ssl.KeyManager;", "[Ljavax.net.ssl.TrustManager;", "java.security.SecureRandom"
    );
    init.implementation = function (keyManagers, _trustManagers, secureRandom) {
      log("SSLContext.init: substituted a trust-all TrustManager");
      init.call(this, keyManagers, Java.array("Ljavax.net.ssl.TrustManager;", trustManagers), secureRandom);
    };
  } catch (e) {
    log("SSLContext/TrustManager hook failed: " + e);
  }

  try {
    var CertificatePinner = Java.use("okhttp3.CertificatePinner");
    CertificatePinner.check.overloads.forEach(function (ov) {
      ov.implementation = function () {
        log("okhttp3.CertificatePinner.check bypassed for " + arguments[0]);
      };
    });
  } catch (e) {
    log("OkHttp CertificatePinner not present or hook failed: " + e);
  }

  try {
    var HttpsURLConnection = Java.use("javax.net.ssl.HttpsURLConnection");
    HttpsURLConnection.setDefaultHostnameVerifier.implementation = function (_verifier) {
      log("HttpsURLConnection.setDefaultHostnameVerifier: ignored app-supplied verifier");
    };
    HttpsURLConnection.setHostnameVerifier.implementation = function (_verifier) {
      log("HttpsURLConnection.setHostnameVerifier: ignored app-supplied verifier");
    };
  } catch (e) {
    log("HostnameVerifier hook failed: " + e);
  }

  send({ type: "notice", message: "universal SSL-pinning bypass attached" });
});
""",
    },
}


def _script_dir() -> Path:
    path = config.DATA_DIR / "sslpinning_scripts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_scripts() -> dict:
    scripts = dict(BYPASS_SCRIPTS)
    for path in sorted(_script_dir().glob("*.js")):
        name = path.stem
        scripts[name] = {
            "readonly": False,
            "description": "Saved SSL-pinning bypass script",
            "source": path.read_text(encoding="utf-8"),
        }
    return scripts


def save_script(name: str, source: str) -> dict:
    name = frida_manager.validate_script_name(name)
    if name in BYPASS_SCRIPTS:
        raise manager.AdbError("built-in scripts are read-only")
    if not source or len(source.encode("utf-8")) > frida_manager.MAX_SCRIPT_BYTES:
        raise manager.AdbError("script source is empty or too large")
    (_script_dir() / f"{name}.js").write_text(source, encoding="utf-8")
    return {"ok": True, "name": name}


def delete_script(name: str) -> dict:
    name = frida_manager.validate_script_name(name)
    if name in BYPASS_SCRIPTS:
        raise manager.AdbError("built-in scripts are read-only")
    path = _script_dir() / f"{name}.js"
    if path.exists():
        path.unlink()
    return {"ok": True}


def attach_bypass(serial: str, target, script_name: str | None, script_source: str | None) -> dict:
    """Attach a bypass script via the shared Frida session registry
    (adb.frida_manager) so the resulting session is manageable through the
    existing /api/frida/sessions/* endpoints, not a parallel one."""
    if script_name and not script_source:
        scripts = list_scripts()
        if script_name not in scripts:
            raise manager.AdbError("script not found")
        script_source = scripts[script_name]["source"]
    if not script_source:
        raise manager.AdbError("missing script_source or script_name")
    session_id = frida_manager.attach(serial, target, script_source)
    return {"ok": True, "session_id": session_id, "script_sha256": frida_manager.script_hash(script_source)}
