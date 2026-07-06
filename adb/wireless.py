"""Wireless (TCP/IP) ADB: enable tcpip mode, connect/disconnect, known-device store."""
import re

import config
from . import manager, network

_HOST_PORT_RE = re.compile(r"^([A-Za-z0-9.\-]+):(\d+)$")
MAX_KNOWN_DEVICE_NAME_LEN = 100


def _valid_host_port(host_port: str) -> bool:
    match = _HOST_PORT_RE.match(host_port)
    return bool(match) and 0 <= int(match.group(2)) <= 65535


def enable_tcpip(serial: str, port: int = 5555) -> dict:
    proc = manager.run(["-s", serial, "tcpip", str(int(port))], timeout=15)
    return {"ok": proc.returncode == 0, "output": (proc.stdout + proc.stderr).strip()[:300]}


def get_device_wifi_address(serial: str, port: int = 5555) -> str | None:
    info = network.get_network_info(serial)
    return f"{info['wifi_ip']}:{port}" if info.get("wifi_ip") else None


def connect(host_port: str) -> dict:
    if not _valid_host_port(host_port):
        return {"ok": False, "error": "invalid_address"}
    proc = manager.run(["connect", host_port], timeout=15)
    output = proc.stdout.strip()
    ok = "connected to" in output.lower() and "cannot" not in output.lower() and "failed" not in output.lower()
    return {"ok": ok, "output": output[:300]}


def disconnect(host_port: str) -> dict:
    if not _valid_host_port(host_port):
        return {"ok": False, "error": "invalid_address"}
    proc = manager.run(["disconnect", host_port], timeout=10)
    return {"ok": proc.returncode == 0, "output": proc.stdout.strip()[:300]}


def list_known_devices() -> dict:
    return config.load_known_devices()


def save_known_device(name: str, host_port: str) -> dict:
    if not isinstance(name, str) or not name.strip() or len(name) > MAX_KNOWN_DEVICE_NAME_LEN:
        return {"ok": False, "error": "invalid_name"}
    if not _valid_host_port(host_port):
        return {"ok": False, "error": "invalid_address"}
    devices = config.load_known_devices()
    devices[name] = host_port
    config.save_known_devices(devices)
    return {"ok": True}


def delete_known_device(name: str) -> dict:
    devices = config.load_known_devices()
    if name in devices:
        del devices[name]
        config.save_known_devices(devices)
    return {"ok": True}


def reconnect_known_devices() -> list[dict]:
    devices = config.load_known_devices()
    results = []
    for name, host_port in devices.items():
        result = connect(host_port)
        results.append({"name": name, "address": host_port, **result})
    return results
