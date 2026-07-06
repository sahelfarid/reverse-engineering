"""Device discovery: `adb devices -l`, per-device properties, battery, storage,
plus fastboot detection (fastboot devices don't show up in `adb devices`).
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import manager

_DEVICES_LINE_RE = re.compile(r"^(?P<serial>\S+)\s+(?P<state>\S+)(?P<rest>.*)$")
_KV_RE = re.compile(r"(\S+):(\S+)")


def _parse_devices_line(line: str) -> dict | None:
    line = line.strip()
    if not line or line.startswith("List of devices"):
        return None
    match = _DEVICES_LINE_RE.match(line)
    if not match:
        return None
    entry = {
        "serial": match.group("serial"),
        "state": match.group("state"),
        "product": None,
        "model": None,
        "device": None,
        "transport_id": None,
        "is_wireless": ":" in match.group("serial"),
    }
    for key, value in _KV_RE.findall(match.group("rest")):
        if key in entry:
            entry[key] = value
    return entry


def list_devices() -> list[dict]:
    proc = manager.run(["devices", "-l"], timeout=10)
    entries = []
    for line in proc.stdout.splitlines():
        parsed = _parse_devices_line(line)
        if parsed:
            entries.append(parsed)
    return entries


def fastboot_path() -> Path | None:
    exe = "fastboot.exe" if os.name == "nt" else "fastboot"
    vendor_fastboot = manager.vendor_adb_path().parent / exe
    if vendor_fastboot.is_file():
        return vendor_fastboot
    system_fastboot = shutil.which("fastboot")
    return Path(system_fastboot) if system_fastboot else None


def list_fastboot_devices() -> list[dict]:
    fb = fastboot_path()
    if fb is None:
        return []
    try:
        proc = subprocess.run([str(fb), "devices"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []
    entries = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        entries.append({"serial": parts[0], "state": "fastboot", "product": None,
                         "model": None, "device": None, "transport_id": None, "is_wireless": False})
    return entries


_PROP_KEYS = {
    "model": "ro.product.model",
    "manufacturer": "ro.product.manufacturer",
    "android_version": "ro.build.version.release",
    "sdk_version": "ro.build.version.sdk",
    "abi": "ro.product.cpu.abi",
    "build_fingerprint": "ro.build.fingerprint",
}


def get_basic_properties(serial: str) -> dict:
    result = {}
    for label, prop in _PROP_KEYS.items():
        stdout, _stderr, rc = manager.shell(serial, f"getprop {manager.quote_remote(prop)}", timeout=5)
        result[label] = stdout.strip() if rc == 0 else None
    return result


def get_battery_info(serial: str) -> dict:
    stdout, _stderr, rc = manager.shell(serial, "dumpsys battery", timeout=5)
    if rc != 0:
        return {"level": None, "status": None, "health": None, "temperature_c": None, "charging": None}
    info = {}
    for line in stdout.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.strip().partition(":")
        info[key.strip().lower()] = value.strip()
    temp_raw = info.get("temperature")
    return {
        "level": int(info["level"]) if info.get("level", "").isdigit() else None,
        "status": info.get("status"),
        "health": info.get("health"),
        "temperature_c": (int(temp_raw) / 10.0) if temp_raw and temp_raw.lstrip("-").isdigit() else None,
        "charging": info.get("ac powered") == "true" or info.get("usb powered") == "true"
        or info.get("wireless powered") == "true",
    }


def get_storage_info(serial: str) -> dict:
    stdout, _stderr, rc = manager.shell(serial, "df /sdcard /data", timeout=5)
    volumes = []
    if rc == 0:
        for line in stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 6:
                volumes.append({
                    "filesystem": parts[0], "size_kb": parts[1], "used_kb": parts[2],
                    "available_kb": parts[3], "use_pct": parts[4], "mounted_on": parts[5],
                })
    return {"volumes": volumes}


def is_root_available(serial: str) -> bool:
    return manager.has_root_shell(serial)


def get_device_detail(serial: str) -> dict:
    manager.validate_serial(serial)
    return {
        "serial": serial,
        "properties": get_basic_properties(serial),
        "battery": get_battery_info(serial),
        "storage": get_storage_info(serial),
        "root_available": is_root_available(serial),
    }
