"""Core ADB primitives: detection, bundled install, and safe command execution.

Every other module in this package builds on run()/shell() here rather than
calling subprocess directly, so the "never build shell commands via string
concatenation" rule lives in exactly one place.
"""
import os
import re
import shlex
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path

import requests

import config

_SERIAL_RE = re.compile(r"^[A-Za-z0-9._:\-]+$")


class AdbError(Exception):
    pass


class AdbNotInstalledError(AdbError):
    pass


class AdbInstallError(AdbError):
    pass


def validate_serial(serial: str) -> str:
    if not serial or not _SERIAL_RE.match(serial):
        raise AdbError(f"Invalid device serial: {serial!r}")
    return serial


def quote_remote(value: str) -> str:
    """Quote a path/argument for safe inclusion in a remote (POSIX-like) shell string."""
    return shlex.quote(value)


def vendor_adb_path() -> Path:
    exe = "adb.exe" if os.name == "nt" else "adb"
    return config.VENDOR_DIR / "platform-tools" / exe


def find_adb() -> Path | None:
    settings = config.load_settings()
    override = settings.get("adb_path_override")
    if override and Path(override).is_file():
        return Path(override)

    vendor = vendor_adb_path()
    if vendor.is_file():
        return vendor

    system_adb = shutil.which("adb")
    if system_adb:
        return Path(system_adb)

    return None


def _adb_version(adb_path: Path) -> str | None:
    try:
        proc = subprocess.run(
            [str(adb_path), "version"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    match = re.search(r"version\s+([\d.]+)", proc.stdout)
    return match.group(1) if match else proc.stdout.strip().splitlines()[0]


def get_adb_status() -> dict:
    adb_path = find_adb()
    if adb_path is None:
        return {"installed": False, "source": None, "version": None, "path": None}

    source = "vendor" if str(adb_path).startswith(str(config.VENDOR_DIR)) else "system"
    version = _adb_version(adb_path)
    return {
        "installed": version is not None,
        "source": source,
        "version": version,
        "path": str(adb_path),
    }


def download_platform_tools(dest_zip: Path, chunk_size: int = 1 << 16) -> Path:
    tag = config.get_platform_tag()
    url = config.PLATFORM_TOOLS_URL_TEMPLATE.format(tag=tag)
    try:
        with requests.get(url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            dest_zip.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_zip, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        fh.write(chunk)
    except requests.RequestException as exc:
        raise AdbInstallError(f"Failed to download platform-tools: {exc}") from exc
    return dest_zip


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract zf into dest, rejecting members that would escape dest via
    ".." segments or absolute paths (zip-slip)."""
    dest_resolved = dest.resolve()
    for member in zf.namelist():
        member_path = (dest_resolved / member).resolve()
        if member_path != dest_resolved and dest_resolved not in member_path.parents:
            raise AdbInstallError(f"Unsafe path in platform-tools archive: {member!r}")
    zf.extractall(dest)


def install_adb() -> dict:
    zip_path = config.TEMP_DIR / "platform-tools.zip"
    try:
        download_platform_tools(zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            _safe_extract(zf, config.VENDOR_DIR)
    except zipfile.BadZipFile as exc:
        raise AdbInstallError(f"Downloaded file is not a valid zip: {exc}") from exc
    finally:
        if zip_path.exists():
            zip_path.unlink()

    adb_path = vendor_adb_path()
    if not adb_path.is_file():
        raise AdbInstallError("adb executable not found after extraction")

    if os.name != "nt":
        adb_path.chmod(adb_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    status = get_adb_status()
    if not status["installed"]:
        raise AdbInstallError("adb was extracted but does not report a valid version")
    return status


def run_binary(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    """Like run(), but captures stdout as raw bytes (for screencap/binary transfers)."""
    adb_path = find_adb()
    if adb_path is None:
        raise AdbNotInstalledError("adb is not installed")
    try:
        return subprocess.run(
            [str(adb_path), *args],
            capture_output=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise AdbError(f"adb command timed out: {' '.join(args)}") from exc


def run(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    """Run adb with argv-list args (never a shell string). Raises AdbNotInstalledError if missing."""
    adb_path = find_adb()
    if adb_path is None:
        raise AdbNotInstalledError("adb is not installed")
    try:
        return subprocess.run(
            [str(adb_path), *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise AdbError(f"adb command timed out: {' '.join(args)}") from exc


def shell(serial: str, remote_command: str, timeout: int | None = None) -> tuple[str, str, int]:
    """Run one already-quoted remote command string via `adb -s <serial> shell <cmd>`.

    The whole remote_command must be a single pre-built string (each dynamic
    path/arg already passed through quote_remote) -- adb joins everything
    after `shell` with spaces before handing it to the device's shell, so
    passing multiple raw argv pieces here would NOT be safe against paths
    containing spaces or shell metacharacters.
    """
    validate_serial(serial)
    settings = config.load_settings()
    effective_timeout = timeout or settings.get("shell_timeout_sec", 20)
    sentinel = "__RC__"
    wrapped = f"{remote_command}; echo {sentinel}:$?"
    proc = run(["-s", serial, "shell", wrapped], timeout=effective_timeout + 5)
    stdout = proc.stdout
    returncode = proc.returncode
    marker_idx = stdout.rfind(f"{sentinel}:")
    if marker_idx != -1:
        body = stdout[:marker_idx].rstrip("\n")
        rc_text = stdout[marker_idx + len(sentinel) + 1:].strip()
        try:
            returncode = int(rc_text)
        except ValueError:
            pass
        stdout = body
    return stdout, proc.stderr, returncode


def has_root_shell(serial: str) -> bool:
    stdout, _stderr, rc = shell(serial, "su -c id", timeout=5)
    return rc == 0 and "uid=" in stdout
