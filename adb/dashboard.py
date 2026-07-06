"""Lightweight composite queries backing the Dashboard tab's overview cards.

These are one-off `dumpsys`/`/proc` reads that don't warrant their own module;
the dedicated screen/process/network modules (added in later phases) own the
deeper versions of similar data and can supersede these where they overlap.
"""
import re

from . import manager


def get_cpu_mem(serial: str) -> dict:
    loadavg, _err, rc1 = manager.shell(serial, "cat /proc/loadavg", timeout=5)
    meminfo, _err2, rc2 = manager.shell(serial, "cat /proc/meminfo", timeout=5)
    result = {"load_1m": None, "load_5m": None, "load_15m": None, "mem_total_kb": None, "mem_available_kb": None}
    if rc1 == 0 and loadavg.strip():
        parts = loadavg.split()
        if len(parts) >= 3:
            result["load_1m"], result["load_5m"], result["load_15m"] = parts[0], parts[1], parts[2]
    if rc2 == 0:
        for line in meminfo.splitlines():
            m = re.match(r"(MemTotal|MemAvailable):\s+(\d+)\s*kB", line)
            if m:
                key = "mem_total_kb" if m.group(1) == "MemTotal" else "mem_available_kb"
                result[key] = int(m.group(2))
    return result


def get_running_apps_count(serial: str) -> dict:
    stdout, _err, rc = manager.shell(serial, "pm list packages -3", timeout=10)
    user_apps = len(stdout.strip().splitlines()) if rc == 0 else None
    stdout_all, _err2, rc2 = manager.shell(serial, "pm list packages", timeout=10)
    total_apps = len(stdout_all.strip().splitlines()) if rc2 == 0 else None
    return {"user_apps": user_apps, "total_apps": total_apps}


def get_screen_status(serial: str) -> dict:
    stdout, _err, rc = manager.shell(serial, "dumpsys power", timeout=5)
    if rc != 0:
        return {"screen_on": None}
    match = re.search(r"mWakefulness=(\w+)", stdout) or re.search(r"Display Power: state=(\w+)", stdout)
    if not match:
        return {"screen_on": None}
    value = match.group(1)
    return {"screen_on": value in ("Awake", "ON")}


def get_foreground_app(serial: str) -> dict:
    stdout, _err, rc = manager.shell(
        serial, "dumpsys activity activities | grep -E 'mResumedActivity|mFocusedApp'", timeout=5
    )
    if rc != 0 or not stdout.strip():
        return {"package": None, "activity": None}
    match = re.search(r"\{[^}]*\s([\w.]+)/([\w.$]+)", stdout)
    if not match:
        return {"package": None, "activity": None}
    return {"package": match.group(1), "activity": match.group(2)}


def get_wifi_status(serial: str) -> dict:
    stdout, _err, rc = manager.shell(serial, "dumpsys wifi | grep -E 'mWifiState|Wi-Fi is'", timeout=5)
    if rc != 0 or not stdout:
        return {"enabled": None}
    lowered = stdout.lower()
    if "enabled" in lowered:
        return {"enabled": True}
    if "disabled" in lowered:
        return {"enabled": False}
    return {"enabled": None}


def get_overview(serial: str) -> dict:
    manager.validate_serial(serial)
    return {
        "cpu_mem": get_cpu_mem(serial),
        "apps": get_running_apps_count(serial),
        "screen": get_screen_status(serial),
        "foreground": get_foreground_app(serial),
        "wifi": get_wifi_status(serial),
        "root_available": manager.has_root_shell(serial),
    }
