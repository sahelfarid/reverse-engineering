"""Screen tools: screenshot, screen recording, rotation, wake/sleep, brightness."""
from . import manager

_ROTATION_VALUES = {0: 0, 90: 1, 180: 2, 270: 3}

# In-memory only (per server process) -- fine for a local single-user dev tool.
_ACTIVE_RECORDINGS: dict[str, dict] = {}


def take_screenshot(serial: str) -> bytes:
    manager.validate_serial(serial)
    proc = manager.run_binary(["-s", serial, "exec-out", "screencap", "-p"], timeout=20)
    if proc.returncode != 0 or not proc.stdout:
        raise manager.AdbError("screenshot failed")
    return proc.stdout


def start_recording(serial: str, remote_path: str = "/sdcard/adbpanel_record.mp4", time_limit_sec: int = 180) -> dict:
    manager.validate_serial(serial)
    if serial in _ACTIVE_RECORDINGS:
        return {"ok": False, "error": "recording_already_active"}
    quoted = manager.quote_remote(remote_path)
    cmd = f"screenrecord --time-limit {int(time_limit_sec)} {quoted} > /dev/null 2>&1 & echo $!"
    stdout, _stderr, rc = manager.shell(serial, cmd, timeout=10)
    pid = stdout.strip().splitlines()[-1] if stdout.strip() else ""
    if rc != 0 or not pid.isdigit():
        return {"ok": False, "error": "failed_to_start"}
    _ACTIVE_RECORDINGS[serial] = {"pid": pid, "remote_path": remote_path}
    return {"ok": True, "pid": pid, "remote_path": remote_path}


def stop_recording(serial: str) -> dict:
    info = _ACTIVE_RECORDINGS.pop(serial, None)
    if not info:
        return {"ok": False, "error": "no_active_recording"}
    manager.shell(serial, f"kill -INT {info['pid']}", timeout=10)
    return {"ok": True, "remote_path": info["remote_path"]}


def recording_status(serial: str) -> dict:
    info = _ACTIVE_RECORDINGS.get(serial)
    return {"active": info is not None, "remote_path": info["remote_path"] if info else None}


def set_rotation(serial: str, degrees: int) -> dict:
    if degrees not in _ROTATION_VALUES:
        return {"ok": False, "error": "invalid_rotation"}
    manager.shell(serial, "settings put system accelerometer_rotation 0", timeout=10)
    _stdout, _stderr, rc = manager.shell(
        serial, f"settings put system user_rotation {_ROTATION_VALUES[degrees]}", timeout=10
    )
    return {"ok": rc == 0}


def unlock_auto_rotation(serial: str) -> dict:
    _stdout, _stderr, rc = manager.shell(serial, "settings put system accelerometer_rotation 1", timeout=10)
    return {"ok": rc == 0}


def wake_device(serial: str) -> dict:
    _stdout, _stderr, rc = manager.shell(serial, "input keyevent KEYCODE_WAKEUP", timeout=10)
    return {"ok": rc == 0}


def sleep_device(serial: str) -> dict:
    _stdout, _stderr, rc = manager.shell(serial, "input keyevent KEYCODE_SLEEP", timeout=10)
    return {"ok": rc == 0}


def set_brightness(serial: str, level: int) -> dict:
    level = max(0, min(255, int(level)))
    _stdout, _stderr, rc = manager.shell(serial, f"settings put system screen_brightness {level}", timeout=10)
    return {"ok": rc == 0}
