"""Backup/export helpers: common media folders, full app data (root/run-as
permitting), single database files, logcat dumps, and screenshot exports --
these compose the existing files.py/packages.py primitives rather than
re-implementing pull/zip.
"""
from pathlib import Path

from . import files as adb_files
from . import manager, packages

COMMON_EXPORT_TARGETS = {
    "photos": "/sdcard/DCIM",
    "downloads": "/sdcard/Download",
    "screenshots": "/sdcard/Pictures/Screenshots",
    "music": "/sdcard/Music",
    "movies": "/sdcard/Movies",
    "documents": "/sdcard/Documents",
}


def resolve_export_path(key: str) -> str | None:
    return COMMON_EXPORT_TARGETS.get(key)


def dump_logcat_to_file(serial: str, local_dir: Path) -> Path:
    manager.validate_serial(serial)
    proc = manager.run(["-s", serial, "logcat", "-d", "-v", "threadtime"], timeout=60)
    local_dir.mkdir(parents=True, exist_ok=True)
    out_path = local_dir / f"logcat-{serial.replace(':', '-')}.txt"
    out_path.write_text(proc.stdout, encoding="utf-8", errors="replace")
    return out_path


def _try_run_as_cat(serial: str, package: str, relative_path: str) -> bytes | None:
    proc = manager.run_binary(
        ["-s", serial, "exec-out", "run-as", package, "cat", relative_path], timeout=60
    )
    return proc.stdout if proc.returncode == 0 and proc.stdout else None


def _try_root_cat(serial: str, absolute_path: str) -> bytes | None:
    if not manager.has_root_shell(serial):
        return None
    proc = manager.run_binary(["-s", serial, "exec-out", "su", "0", "cat", absolute_path], timeout=60)
    return proc.stdout if proc.returncode == 0 and proc.stdout else None


def export_database(serial: str, package: str, db_name: str, local_dir: Path) -> Path:
    packages.validate_package(package)
    if "/" in db_name or db_name in (".", ".."):
        raise manager.AdbError("invalid database name")

    data = _try_run_as_cat(serial, package, f"databases/{db_name}")
    if data is None:
        data = _try_root_cat(serial, f"/data/data/{package}/databases/{db_name}")
    if data is None:
        raise manager.AdbError(
            "App data is not accessible: requires the app to be debuggable (run-as) or a rooted device."
        )

    local_dir.mkdir(parents=True, exist_ok=True)
    out_path = local_dir / db_name
    out_path.write_bytes(data)
    return out_path


def export_app_data(serial: str, package: str, local_dir: Path) -> Path:
    packages.validate_package(package)
    remote_tmp = f"/data/local/tmp/{package}_data.tar.gz"
    quoted_tmp = manager.quote_remote(remote_tmp)

    stdout, stderr, rc = manager.shell(
        serial, f"run-as {manager.quote_remote(package)} tar -czf {quoted_tmp} -C /data/data/{package} .", timeout=180
    )
    used_root = False
    if rc != 0:
        if not manager.has_root_shell(serial):
            raise manager.AdbError(
                "App data is not accessible: requires the app to be debuggable (run-as) or a rooted device."
            )
        manager.shell(serial, f"su 0 tar -czf {quoted_tmp} -C /data/data/{package} .", timeout=180)
        used_root = True

    try:
        local_path = adb_files.pull_file(serial, remote_tmp, local_dir)
    finally:
        cleanup_cmd = f"rm -f {quoted_tmp}"
        if used_root:
            manager.shell(serial, f"su 0 {cleanup_cmd}", timeout=15)
        else:
            manager.shell(serial, cleanup_cmd, timeout=15)
    return local_path
