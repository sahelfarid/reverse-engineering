"""APK/package management: list, install/uninstall, enable/disable, clear, launch, pull."""
import re
from pathlib import Path

from . import manager

_PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")


def validate_package(package: str) -> str:
    if not package or not _PACKAGE_RE.match(package):
        raise manager.AdbError(f"Invalid package name: {package!r}")
    return package


def _parse_dumpsys_packages(stdout: str) -> dict:
    blocks = re.split(r"\n(?=  Package \[)", stdout)
    result = {}
    for block in blocks:
        header = re.match(r"\s*Package \[([\w.]+)\]", block)
        if not header:
            continue
        pkg = header.group(1)
        version_name = re.search(r"versionName=(\S+)", block)
        version_code = re.search(r"versionCode=(\d+)", block)
        code_path = re.search(r"codePath=(\S+)", block)
        first_install = re.search(r"firstInstallTime=([^\n]+)", block)
        last_update = re.search(r"lastUpdateTime=([^\n]+)", block)
        flags = re.search(r"pkgFlags=\[([^\]]*)\]", block)
        result[pkg] = {
            "package": pkg,
            "version_name": version_name.group(1) if version_name else None,
            "version_code": version_code.group(1) if version_code else None,
            "code_path": code_path.group(1) if code_path else None,
            "first_install_time": first_install.group(1).strip() if first_install else None,
            "last_update_time": last_update.group(1).strip() if last_update else None,
            "is_system": bool(flags and "SYSTEM" in flags.group(1)),
        }
    return result


def list_packages(serial: str) -> list[dict]:
    stdout, _stderr, rc = manager.shell(serial, "dumpsys package packages", timeout=30)
    if rc != 0:
        raise manager.AdbError("failed to list packages")
    parsed = _parse_dumpsys_packages(stdout)
    if not parsed:
        # Fallback for devices where dumpsys output format didn't match: minimal listing.
        stdout2, _e, rc2 = manager.shell(serial, "pm list packages -f", timeout=20)
        if rc2 != 0:
            return []
        entries = []
        for line in stdout2.splitlines():
            m = re.match(r"package:(.+)=([\w.]+)$", line.strip())
            if m:
                entries.append({"package": m.group(2), "code_path": m.group(1), "version_name": None,
                                 "version_code": None, "first_install_time": None, "last_update_time": None,
                                 "is_system": m.group(1).startswith("/system/")})
        return entries
    return sorted(parsed.values(), key=lambda p: p["package"])


def get_apk_path(serial: str, package: str) -> str | None:
    validate_package(package)
    stdout, _stderr, rc = manager.shell(serial, f"pm path {manager.quote_remote(package)}", timeout=10)
    if rc != 0:
        return None
    lines = [l.split("package:", 1)[-1] for l in stdout.splitlines() if l.startswith("package:")]
    return lines[0] if lines else None


def get_apk_size(serial: str, apk_path: str) -> int | None:
    stdout, _stderr, rc = manager.shell(serial, f"stat -c %s {manager.quote_remote(apk_path)}", timeout=10)
    return int(stdout.strip()) if rc == 0 and stdout.strip().isdigit() else None


def install_apk(serial: str, local_apk: Path) -> dict:
    proc = manager.run(["-s", serial, "install", "-r", str(local_apk)], timeout=120)
    return {"ok": proc.returncode == 0 and "Success" in proc.stdout,
            "output": (proc.stdout + proc.stderr).strip()[:2000]}


def install_multiple_apks(serial: str, local_apks: list[Path]) -> dict:
    proc = manager.run(["-s", serial, "install-multiple", "-r", *[str(p) for p in local_apks]], timeout=180)
    return {"ok": proc.returncode == 0 and "Success" in proc.stdout,
            "output": (proc.stdout + proc.stderr).strip()[:2000]}


def uninstall_apk(serial: str, package: str, keep_data: bool = False) -> dict:
    validate_package(package)
    args = ["-s", serial, "uninstall"] + (["-k"] if keep_data else []) + [package]
    proc = manager.run(args, timeout=60)
    return {"ok": proc.returncode == 0 and "Success" in proc.stdout,
            "output": (proc.stdout + proc.stderr).strip()[:2000]}


def _pm_action(serial: str, package: str, sub: str) -> dict:
    validate_package(package)
    stdout, stderr, rc = manager.shell(serial, f"pm {sub} {manager.quote_remote(package)}", timeout=20)
    return {"ok": rc == 0, "output": (stdout + stderr).strip()[:500]}


def disable_package(serial: str, package: str) -> dict:
    return _pm_action(serial, package, "disable-user --user 0")


def enable_package(serial: str, package: str) -> dict:
    return _pm_action(serial, package, "enable")


def clear_data(serial: str, package: str) -> dict:
    return _pm_action(serial, package, "clear")


def force_stop(serial: str, package: str) -> dict:
    validate_package(package)
    stdout, stderr, rc = manager.shell(serial, f"am force-stop {manager.quote_remote(package)}", timeout=15)
    return {"ok": rc == 0, "output": (stdout + stderr).strip()[:500]}


def launch_app(serial: str, package: str) -> dict:
    validate_package(package)
    stdout, stderr, rc = manager.shell(
        serial, f"monkey -p {manager.quote_remote(package)} -c android.intent.category.LAUNCHER 1", timeout=15
    )
    ok = rc == 0 and "no activities" not in (stdout + stderr).lower()
    return {"ok": ok, "output": (stdout + stderr).strip()[:500]}


def restart_app(serial: str, package: str) -> dict:
    force_stop(serial, package)
    return launch_app(serial, package)


def pull_apk(serial: str, package: str, local_dir: Path) -> Path:
    apk_path = get_apk_path(serial, package)
    if not apk_path:
        raise manager.AdbError(f"could not resolve apk path for {package}")
    local_dir.mkdir(parents=True, exist_ok=True)
    proc = manager.run(["-s", serial, "pull", apk_path, str(local_dir)], timeout=180)
    if proc.returncode != 0:
        raise manager.AdbError(f"pull failed: {proc.stderr.strip()[:300]}")
    dest = local_dir / f"{package}.apk"
    pulled_name = local_dir / Path(apk_path).name
    if pulled_name.exists():
        pulled_name.rename(dest)
        return dest
    return pulled_name
