"""Live logcat streaming (threadtime format) with server-side tag/pid/level/regex filtering."""
import re
import subprocess

from . import manager

_LEVEL_ORDER = {"V": 0, "D": 1, "I": 2, "W": 3, "E": 4, "F": 5, "S": 6}
_LINE_RE = re.compile(
    r"^(?P<date>\d\d-\d\d)\s+(?P<time>\d\d:\d\d:\d\d\.\d+)\s+(?P<pid>\d+)\s+(?P<tid>\d+)\s+"
    r"(?P<level>[VDIWEFS])\s+(?P<tag>[^:]*):\s?(?P<message>.*)$"
)


def parse_logcat_line(line: str) -> dict:
    match = _LINE_RE.match(line)
    if not match:
        return {"raw": line, "level": None, "tag": None, "pid": None, "message": line, "parseable": False}
    d = match.groupdict()
    return {"raw": line, "date": d["date"], "time": d["time"], "pid": d["pid"], "tid": d["tid"],
            "level": d["level"], "tag": d["tag"].strip(), "message": d["message"], "parseable": True}


def resolve_pid(serial: str, package: str) -> str | None:
    stdout, _stderr, rc = manager.shell(serial, f"pidof {manager.quote_remote(package)}", timeout=10)
    if rc == 0 and stdout.strip():
        return stdout.strip().split()[0]
    return None


def clear_logcat(serial: str) -> dict:
    proc = manager.run(["-s", serial, "logcat", "-c"], timeout=15)
    return {"ok": proc.returncode == 0}


def stream_logcat(serial: str, tag: str | None, pid: str | None, min_level: str | None, query: str | None):
    manager.validate_serial(serial)
    adb_path = manager.find_adb()
    if adb_path is None:
        raise manager.AdbNotInstalledError("adb is not installed")

    min_rank = _LEVEL_ORDER.get((min_level or "V").upper(), 0)
    try:
        query_re = re.compile(query, re.IGNORECASE) if query else None
    except re.error as exc:
        raise manager.AdbError(f"invalid regex query: {exc}") from exc

    process = subprocess.Popen(
        [str(adb_path), "-s", serial, "logcat", "-v", "threadtime"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1,
    )
    try:
        for raw_line in process.stdout:
            entry = parse_logcat_line(raw_line.rstrip("\n"))
            if tag and entry.get("tag") != tag:
                continue
            if pid and entry.get("pid") != str(pid):
                continue
            if entry.get("level") and _LEVEL_ORDER.get(entry["level"], 0) < min_rank:
                continue
            if query_re and not query_re.search(entry["raw"]):
                continue
            yield entry
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
