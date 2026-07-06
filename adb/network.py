"""Network info + adb port forwarding/reverse-forwarding."""
import re

from . import manager

_PORT_SPEC_RE = re.compile(r"^(tcp|udp):\d+$")


def get_network_info(serial: str) -> dict:
    manager.validate_serial(serial)
    ip_out, _e1, _rc1 = manager.shell(serial, "ip addr show wlan0", timeout=10)
    ip_match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/(\d+)", ip_out)

    route_out, _e2, _rc2 = manager.shell(serial, "ip route", timeout=10)
    gateway_match = re.search(r"default via (\S+)", route_out)

    dns1, _e3, _rc3 = manager.shell(serial, "getprop net.dns1", timeout=5)
    dns2, _e4, _rc4 = manager.shell(serial, "getprop net.dns2", timeout=5)

    network_type, _e5, _rc5 = manager.shell(serial, "getprop gsm.network.type", timeout=5)
    wifi_state, _e6, _rc6 = manager.shell(serial, "dumpsys wifi | grep -m1 'mWifiState\\|Wi-Fi is'", timeout=5)

    return {
        "wifi_ip": ip_match.group(1) if ip_match else None,
        "wifi_prefix": ip_match.group(2) if ip_match else None,
        "gateway": gateway_match.group(1) if gateway_match else None,
        "dns1": dns1.strip() or None,
        "dns2": dns2.strip() or None,
        "mobile_network_type": network_type.strip() or None,
        "wifi_state_raw": wifi_state.strip() or None,
    }


def ping_from_device(serial: str, host: str, count: int = 4) -> dict:
    manager.validate_serial(serial)
    if not re.match(r"^[A-Za-z0-9.\-]+$", host):
        return {"ok": False, "error": "invalid_host"}
    stdout, stderr, rc = manager.shell(serial, f"ping -c {int(count)} -W 2 {manager.quote_remote(host)}", timeout=count * 3 + 5)
    return {"ok": rc == 0, "output": (stdout + stderr).strip()[-2000:]}


def _validate_port_spec(spec: str) -> str:
    if not _PORT_SPEC_RE.match(spec):
        raise manager.AdbError(f"invalid port spec: {spec!r} (expected tcp:<port> or udp:<port>)")
    return spec


def list_forwards() -> list[dict]:
    proc = manager.run(["forward", "--list"], timeout=10)
    entries = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3:
            entries.append({"serial": parts[0], "local": parts[1], "remote": parts[2]})
    return entries


def add_forward(serial: str, local: str, remote: str) -> dict:
    _validate_port_spec(local)
    _validate_port_spec(remote)
    proc = manager.run(["-s", serial, "forward", local, remote], timeout=10)
    return {"ok": proc.returncode == 0, "error": None if proc.returncode == 0 else proc.stderr.strip()[:300]}


def remove_forward(local: str) -> dict:
    _validate_port_spec(local)
    proc = manager.run(["forward", "--remove", local], timeout=10)
    return {"ok": proc.returncode == 0}


def list_reverses(serial: str) -> list[dict]:
    proc = manager.run(["-s", serial, "reverse", "--list"], timeout=10)
    entries = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3:
            entries.append({"serial": parts[0], "remote": parts[1], "local": parts[2]})
    return entries


def add_reverse(serial: str, remote: str, local: str) -> dict:
    _validate_port_spec(remote)
    _validate_port_spec(local)
    proc = manager.run(["-s", serial, "reverse", remote, local], timeout=10)
    return {"ok": proc.returncode == 0, "error": None if proc.returncode == 0 else proc.stderr.strip()[:300]}


def remove_reverse(serial: str, remote: str) -> dict:
    _validate_port_spec(remote)
    proc = manager.run(["-s", serial, "reverse", "--remove", remote], timeout=10)
    return {"ok": proc.returncode == 0}
