"""Root / device-integrity indicators.

Complements manager.has_root_shell() (the authoritative "can we get a root
shell right now" check) with a fuller, transparent checklist: every indicator
carries the raw evidence that produced it, and summarize() shows which
indicators drove the verdict rather than collapsing to an opaque boolean.

Host-side, best-effort only: sophisticated hiding (Magisk DenyList scoped to
the shell UID, a custom kernel exposing root to select UIDs) can defeat all of
these from an adb-shell vantage point. The only authoritative check is Google's
Play Integrity API, which runs inside an app on-device, not from the host.
"""
from . import manager

# Common su binary locations checked by most root-detection libraries.
SU_PATHS = [
    "/system/bin/su", "/system/xbin/su", "/sbin/su", "/system/sd/xbin/su",
    "/data/local/xbin/su", "/data/local/bin/su", "/system/bin/failsafe/su",
    "/system/usr/we-need-root/su", "/su/bin/su", "/data/local/su", "/magisk/.core/bin/su",
]

MAGISK_ARTIFACT_PATHS = [
    "/sbin/.magisk", "/cache/magisk.log", "/data/adb/magisk",
    "/data/adb/modules", "/init.magisk.rc",
]

MAGISK_PACKAGE = "com.topjohnwu.magisk"

_BUILD_PROPS = {
    "build_tags": "ro.build.tags",
    "debuggable": "ro.debuggable",
    "secure": "ro.secure",
    "verified_boot_state": "ro.boot.verifiedbootstate",
    "bootloader_locked": "ro.boot.flash.locked",
}


def _batched_path_check(serial: str, paths: list[str]) -> list[str]:
    """Return the subset of `paths` that exist on the device, in one round trip."""
    quoted = " ".join(manager.quote_remote(p) for p in paths)
    # $p is expanded on-device; the candidate paths are pre-quoted literals.
    cmd = f'for p in {quoted}; do [ -e "$p" ] && echo "$p"; done'
    stdout, _stderr, _rc = manager.shell(serial, cmd, timeout=10)
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def check_su_paths(serial: str) -> list[str]:
    return _batched_path_check(serial, SU_PATHS)


def check_magisk(serial: str) -> dict:
    # Direct `pm path` resolves the app even when it's hidden from `pm list
    # packages` for specific targets, unless the shell UID itself is on the
    # DenyList (rare). This is more reliable than scanning the package list.
    stdout, _stderr, rc = manager.shell(serial, f"pm path {manager.quote_remote(MAGISK_PACKAGE)}", timeout=10)
    app_installed = rc == 0 and "package:" in stdout
    artifacts = _batched_path_check(serial, MAGISK_ARTIFACT_PATHS)
    return {"app_installed": app_installed, "artifacts": artifacts}


def check_busybox(serial: str) -> str | None:
    stdout, _stderr, rc = manager.shell(serial, "which busybox", timeout=10)
    path = stdout.strip()
    return path if rc == 0 and path else None


def check_build_integrity(serial: str) -> dict:
    """Read all build/boot integrity properties + SELinux mode in one round trip."""
    parts = [f"echo {label}=$(getprop {manager.quote_remote(prop)})" for label, prop in _BUILD_PROPS.items()]
    parts.append("echo selinux=$(getenforce 2>/dev/null)")
    cmd = "; ".join(parts)
    stdout, _stderr, _rc = manager.shell(serial, cmd, timeout=10)

    values: dict[str, str | None] = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip() or None

    return {
        "build_tags": values.get("build_tags"),
        "debuggable": values.get("debuggable"),
        "secure": values.get("secure"),
        "verified_boot_state": values.get("verified_boot_state"),
        "bootloader_locked": values.get("bootloader_locked"),
        "selinux": values.get("selinux"),
    }


def summarize(indicators: dict) -> dict:
    """Turn the raw indicator set into a verdict + the list of signals behind it.

    Weighting:
      strong   - a working root shell (su -c id -> uid=0)
      moderate - su binary on disk, Magisk app, or Magisk filesystem artifacts
      weak     - test-keys build, debuggable/insecure build, permissive SELinux,
                 or an unlocked bootloader (precondition/side-effect of rooting,
                 not proof on its own)
    """
    matched: list[str] = []

    working_root = indicators.get("working_root_shell")
    su_paths = indicators.get("su_paths") or []
    magisk = indicators.get("magisk") or {}
    busybox = indicators.get("busybox")
    build = indicators.get("build_integrity") or {}

    if working_root:
        matched.append("Working root shell (su -c id returned uid=0)")
    for p in su_paths:
        matched.append(f"su binary present: {p}")
    if magisk.get("app_installed"):
        matched.append("Magisk app installed")
    for a in magisk.get("artifacts", []):
        matched.append(f"Magisk artifact: {a}")

    strong = bool(working_root)
    moderate = bool(su_paths) or magisk.get("app_installed") or bool(magisk.get("artifacts"))

    weak = []
    if build.get("build_tags") and "test-keys" in build["build_tags"]:
        weak.append("Build signed with test-keys")
    if build.get("debuggable") == "1":
        weak.append("Debuggable build (ro.debuggable=1)")
    if build.get("secure") == "0":
        weak.append("Insecure build (ro.secure=0)")
    if build.get("selinux") and build["selinux"].lower() != "enforcing":
        weak.append(f"SELinux not enforcing ({build['selinux']})")
    if build.get("bootloader_locked") == "0":
        weak.append("Bootloader unlocked (ro.boot.flash.locked=0)")
    if busybox:
        weak.append(f"busybox present: {busybox}")
    matched.extend(weak)

    if strong:
        verdict = "rooted"
    elif moderate:
        verdict = "likely rooted"
    elif weak:
        verdict = "possibly modified"
    else:
        verdict = "not detected"

    return {"verdict": verdict, "matched_indicators": matched}


def get_integrity_report(serial: str) -> dict:
    manager.validate_serial(serial)
    su_paths = check_su_paths(serial)
    magisk = check_magisk(serial)
    busybox = check_busybox(serial)
    build_integrity = check_build_integrity(serial)
    working_root_shell = manager.has_root_shell(serial)

    indicators = {
        "working_root_shell": working_root_shell,
        "su_paths": su_paths,
        "magisk": magisk,
        "busybox": busybox,
        "build_integrity": build_integrity,
    }
    summary = summarize(indicators)
    return {
        **summary,
        "indicators": indicators,
        "disclaimer": (
            "Host-side, best-effort detection. Sophisticated root-hiding (Magisk "
            "DenyList, custom kernels) can defeat every check above. This does not "
            "replace Play Integrity / SafetyNet, which must be evaluated on-device."
        ),
    }
