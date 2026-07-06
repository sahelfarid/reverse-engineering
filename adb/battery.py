"""Deeper battery/hardware info beyond the Dashboard tab's summary card."""
import re

from . import devices, manager


def get_battery_detail(serial: str) -> dict:
    basic = devices.get_battery_info(serial)
    stdout, _stderr, rc = manager.shell(serial, "dumpsys battery", timeout=5)
    voltage = technology = cycle_count = None
    if rc == 0:
        for line in stdout.splitlines():
            key, _, value = line.strip().partition(":")
            key, value = key.strip().lower(), value.strip()
            if key == "voltage":
                voltage = value
            elif key == "technology":
                technology = value
            elif key in ("cycle count", "charge counter cycle count"):
                cycle_count = value
    return {**basic, "voltage_mv": voltage, "technology": technology, "cycle_count": cycle_count}


def get_cpu_info(serial: str) -> dict:
    stdout, _stderr, rc = manager.shell(serial, "cat /proc/cpuinfo", timeout=10)
    if rc != 0:
        return {"cores": None, "hardware": None, "model": None}
    cores = len(re.findall(r"^processor\s*:", stdout, re.MULTILINE))
    hardware = re.search(r"^Hardware\s*:\s*(.+)$", stdout, re.MULTILINE)
    model = re.search(r"^model name\s*:\s*(.+)$", stdout, re.MULTILINE)
    return {"cores": cores or None, "hardware": hardware.group(1).strip() if hardware else None,
             "model": model.group(1).strip() if model else None}


def get_gpu_info(serial: str) -> dict:
    stdout, _stderr, rc = manager.shell(serial, "getprop ro.hardware.egl", timeout=5)
    egl = stdout.strip() if rc == 0 and stdout.strip() else None
    stdout2, _e2, rc2 = manager.shell(serial, "dumpsys SurfaceFlinger | grep -i GLES", timeout=10)
    renderer = stdout2.strip().splitlines()[0] if rc2 == 0 and stdout2.strip() else None
    return {"egl": egl, "renderer": renderer}


def get_sensors(serial: str) -> list[str]:
    stdout, _stderr, rc = manager.shell(serial, "dumpsys sensorservice", timeout=10)
    if rc != 0:
        return []
    names = re.findall(r'name="([^"]+)"', stdout)
    if not names:
        names = re.findall(r"^\s*\d+\)\s+(.+?),\s+vendor", stdout, re.MULTILINE)
    return sorted(set(names))[:100]


def get_disk_usage(serial: str) -> list[dict]:
    stdout, _stderr, rc = manager.shell(serial, "df -h", timeout=10)
    if rc != 0:
        return []
    volumes = []
    for line in stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 6:
            volumes.append({"filesystem": parts[0], "size": parts[1], "used": parts[2],
                             "available": parts[3], "use_pct": parts[4], "mounted_on": parts[5]})
    return volumes


def get_hardware_detail(serial: str) -> dict:
    manager.validate_serial(serial)
    return {
        "battery": get_battery_detail(serial),
        "cpu": get_cpu_info(serial),
        "gpu": get_gpu_info(serial),
        "sensors": get_sensors(serial),
        "disk": get_disk_usage(serial),
    }
