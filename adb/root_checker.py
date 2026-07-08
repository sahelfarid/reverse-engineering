"""Per-package root-detection checker: does *this app* try to detect root?

Complements adb/root_detection.py (which asks "is the device rooted") with a
per-app question answered two ways, each independently best-effort:

  static  - pattern-scan the app's already-decompiled JADX sources (if a
            project exists for the package -- see adb/jadx_manager.py) for
            known root-check idioms (su path strings, RootBeer, Build.TAGS,
            Magisk/SuperSU package lookups, etc).
  dynamic - spawn the app under Frida with an observer script that hooks the
            same idioms at runtime and reports what actually fired during a
            short window, then detach. No behavior is altered (no bypass),
            this only *observes*.

Evidence-based, same shape as root_detection.summarize(): a verdict plus the
matched indicators behind it, not just a boolean.
"""
from __future__ import annotations

import re
import time

from . import frida_manager, jadx_manager, manager, packages

_MAX_SCANNED_FILES = 20_000
_MAX_FILE_BYTES = 2 * 1024 * 1024

# (finding id, severity, pattern) -- matched line-by-line against decompiled
# Java sources. These look for the app *checking for* root, not for root
# itself, so they're deliberately narrower than jadx_manager's general
# security findings.
_STATIC_PATTERNS: list[tuple[str, str, "re.Pattern"]] = [
    ("su-path-string", "medium", re.compile(r'"(?:/system/xbin|/system/bin|/sbin|/su/bin|/data/local/xbin|/data/local/bin)/su"')),
    ("su-command-exec", "medium", re.compile(r'exec\([^)]*"su"')),
    ("which-su-check", "medium", re.compile(r'"which\s+su"')),
    ("rootbeer-library", "high", re.compile(r"com\.scottyab\.rootbeer")),
    ("rootcloak-detection", "medium", re.compile(r"com\.devadvance\.rootcloak")),
    ("build-tags-test-keys", "low", re.compile(r"Build\.TAGS|test-keys")),
    ("magisk-package-lookup", "high", re.compile(r"com\.topjohnwu\.magisk")),
    ("supersu-package-lookup", "medium", re.compile(r"eu\.chainfire\.supersu|com\.noshufou\.android\.su|com\.koushikdutta\.superuser")),
    ("busybox-check", "low", re.compile(r'"busybox"')),
    ("safetynet-attestation", "low", re.compile(r"SafetyNet|com\.google\.android\.gms\.safetynet")),
    ("play-integrity-api", "low", re.compile(r"com\.google\.android\.play\.core\.integrity")),
    ("root-check-method-name", "low", re.compile(r"\b(?:isRooted|isDeviceRooted|checkRoot|detectRoot)\w*\s*\(")),
]

# Dynamic observer: hooks the same idioms live and `send()`s a hit for each
# one triggered, tagged so get_report() can pull just these out of whatever
# else the script might log. Purely observational -- nothing here alters
# return values or otherwise bypasses a check.
DYNAMIC_OBSERVER_SCRIPT = r"""
Java.perform(function () {
  function hit(check, detail) {
    send({ type: "root_check_hit", check: check, detail: String(detail) });
  }

  try {
    var File = Java.use("java.io.File");
    var suspicious = [
      "/system/xbin/su", "/system/bin/su", "/sbin/su", "/su/bin/su",
      "/data/local/xbin/su", "/data/local/bin/su", "/system/app/Superuser.apk"
    ];
    var exists = File.exists.overload();
    exists.implementation = function () {
      var path = this.getAbsolutePath();
      if (suspicious.indexOf(path) !== -1) hit("file_exists_su_path", path);
      return exists.call(this);
    };
  } catch (e) {}

  try {
    var Runtime = Java.use("java.lang.Runtime");
    var execStr = Runtime.exec.overload("java.lang.String");
    execStr.implementation = function (cmd) {
      if (cmd && (cmd.indexOf("su") !== -1 || cmd.indexOf("busybox") !== -1)) hit("runtime_exec", cmd);
      return execStr.call(this, cmd);
    };
    var execArr = Runtime.exec.overload("[Ljava.lang.String;");
    execArr.implementation = function (cmdArr) {
      var joined = cmdArr && cmdArr.join ? cmdArr.join(" ") : String(cmdArr);
      if (joined.indexOf("su") !== -1 || joined.indexOf("busybox") !== -1) hit("runtime_exec", joined);
      return execArr.call(this, cmdArr);
    };
  } catch (e) {}

  try {
    var PackageManager = Java.use("android.app.ApplicationPackageManager");
    var rootPkgs = [
      "com.topjohnwu.magisk", "eu.chainfire.supersu",
      "com.noshufou.android.su", "com.koushikdutta.superuser"
    ];
    var getPackageInfo = PackageManager.getPackageInfo.overload("java.lang.String", "int");
    getPackageInfo.implementation = function (pkg, flags) {
      if (rootPkgs.indexOf(pkg) !== -1) hit("package_query_root_app", pkg);
      return getPackageInfo.call(this, pkg, flags);
    };
  } catch (e) {}

  send({ type: "notice", message: "root-detection observer attached" });
});
"""


def static_scan(package: str) -> dict:
    """Pattern-scan an already-decompiled JADX project for this package, if
    one exists. Returns {"available": False, "reason": ...} rather than
    raising when there's no project -- decompiling on demand here would make
    a "run a quick check" endpoint silently kick off a slow jadx job."""
    root = jadx_manager.project_dir(package)
    if not root.is_dir():
        return {"available": False, "reason": "no JADX project decompiled for this package yet", "findings": []}

    findings: list[dict] = []
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
            for finding_id, severity, pattern in _STATIC_PATTERNS:
                if pattern.search(line):
                    findings.append({
                        "id": finding_id, "severity": severity, "file": rel, "line": lineno,
                        "snippet": line.strip()[:300],
                    })
    return {"available": True, "findings": findings}


def observe_dynamic(serial: str, package: str, duration_sec: float = 4.0) -> dict:
    """Spawn `package` under Frida with the observer script, collect hits for
    `duration_sec`, then detach. Best-effort: any AdbError (no frida-server,
    no root, spawn failure) is reported, not raised, so a route can still
    return the static half of the report."""
    try:
        session_id = frida_manager.attach(serial, {"spawn": package}, DYNAMIC_OBSERVER_SCRIPT)
    except manager.AdbError as exc:
        return {"available": False, "reason": str(exc), "events": []}

    try:
        raw = frida_manager.drain_messages(session_id, duration_sec)
    finally:
        frida_manager.detach(session_id)

    events = []
    for item in raw:
        payload = (item.get("message") or {}).get("payload")
        if isinstance(payload, dict) and payload.get("type") == "root_check_hit":
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
        verdict = "root detection implemented (static + dynamic evidence)"
    elif has_static or has_dynamic:
        verdict = "root detection likely implemented"
    else:
        verdict = "no root detection evidence found"

    return {"verdict": verdict, "matched_indicators": matched}


def get_report(
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
            "Best-effort evidence from static source patterns and a short dynamic observation "
            "window. Absence of matches does not prove the app has no root detection -- "
            "obfuscated, native, or reflection-based checks may not match these patterns or "
            "trigger during the observed window."
        ),
    }
