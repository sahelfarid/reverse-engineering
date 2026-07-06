"""Running process list + kill, plus the foreground app (reused from dashboard.py
rather than re-implemented here)."""
import re

from . import dashboard, manager

get_foreground_app = dashboard.get_foreground_app  # re-export, single implementation


def list_processes(serial: str) -> dict:
    manager.validate_serial(serial)
    stdout, _stderr, rc = manager.shell(serial, "ps -A -o PID,PPID,USER,RSS,NAME 2>/dev/null", timeout=15)
    if rc != 0 or not stdout.strip():
        stdout, _stderr, rc = manager.shell(serial, "ps -A", timeout=15)
        if rc != 0 or not stdout.strip():
            return {"processes": [], "parseable": False}

    lines = stdout.strip().splitlines()
    header = re.split(r"\s+", lines[0].strip().upper())
    col_index = {name: i for i, name in enumerate(header)}
    pid_idx = col_index.get("PID")
    name_idx = col_index.get("NAME") or col_index.get("CMD") or col_index.get("COMMAND")
    ppid_idx = col_index.get("PPID")
    user_idx = col_index.get("USER")
    rss_idx = col_index.get("RSS")

    processes = []
    all_parseable = pid_idx is not None and name_idx is not None
    for line in lines[1:]:
        parts = re.split(r"\s+", line.strip(), maxsplit=len(header) - 1)
        if len(parts) < len(header):
            all_parseable = False
            continue
        try:
            pid = int(parts[pid_idx]) if pid_idx is not None else None
        except (ValueError, TypeError):
            pid = None
            all_parseable = False
        processes.append({
            "pid": pid,
            "ppid": parts[ppid_idx] if ppid_idx is not None and ppid_idx < len(parts) else None,
            "user": parts[user_idx] if user_idx is not None and user_idx < len(parts) else None,
            "rss_kb": parts[rss_idx] if rss_idx is not None and rss_idx < len(parts) else None,
            "name": parts[name_idx] if name_idx is not None and name_idx < len(parts) else " ".join(parts),
        })
    processes.sort(key=lambda p: (p["pid"] is None, p["pid"]))
    return {"processes": processes, "parseable": all_parseable}


def kill_process(serial: str, pid: int, sig: str = "TERM") -> dict:
    pid = int(pid)
    sig = re.sub(r"[^A-Z0-9]", "", sig.upper()) or "TERM"
    _stdout, stderr, rc = manager.shell(serial, f"kill -{sig} {pid}", timeout=10)
    if rc == 0:
        return {"ok": True}
    if manager.has_root_shell(serial):
        _stdout2, stderr2, rc2 = manager.shell(serial, f"su 0 kill -{sig} {pid}", timeout=10)
        if rc2 == 0:
            return {"ok": True, "used_root": True}
        return {"ok": False, "error": stderr2.strip()[:300]}
    return {"ok": False, "error": stderr.strip()[:300] or "permission_denied (try a rooted device)"}
