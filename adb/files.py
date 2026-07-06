"""Device file manager: browse/search/preview + CRUD (mkdir/rename/move/copy/delete)
+ transfer (pull/push) + zip packaging for folder downloads.
"""
import re
import shutil
import tempfile
from pathlib import Path

from . import manager

_LS_LINE_RE = re.compile(
    r"^(?P<perms>[bcdlsp\-][rwxstST\-]{9})\+?\s+(?P<links>\d+)\s+(?P<owner>\S+)\s+(?P<group>\S+)\s+"
    r"(?P<size>\d+)\s+(?P<date>\S+)\s+(?P<time>\S+)\s+(?P<name>.+)$"
)

PREVIEWABLE_TEXT_EXT = {".txt", ".log", ".json", ".xml", ".conf", ".properties", ".ini", ".csv", ".md", ".yaml", ".yml"}
PREVIEWABLE_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


def _entry_type(perms: str) -> str:
    return {"d": "dir", "l": "symlink", "b": "block", "c": "char", "s": "socket", "p": "fifo"}.get(perms[0], "file")


def _parse_ls_line(line: str) -> dict | None:
    line = line.rstrip("\r")
    if not line.strip() or line.startswith("total "):
        return None
    match = _LS_LINE_RE.match(line)
    if not match:
        return {"name": line.strip(), "type": "unknown", "size": None, "mtime": None,
                "perms": None, "is_symlink": False, "symlink_target": None, "parseable": False}
    name = match.group("name")
    symlink_target = None
    entry_type = _entry_type(match.group("perms"))
    if entry_type == "symlink" and " -> " in name:
        name, _, symlink_target = name.partition(" -> ")
    return {
        "name": name,
        "type": entry_type,
        "size": int(match.group("size")),
        "mtime": f"{match.group('date')} {match.group('time')}",
        "perms": match.group("perms"),
        "is_symlink": entry_type == "symlink",
        "symlink_target": symlink_target,
        "parseable": True,
    }


def list_directory(serial: str, remote_path: str) -> dict:
    manager.validate_serial(serial)
    quoted = manager.quote_remote(remote_path)
    stdout, stderr, rc = manager.shell(serial, f"ls -la {quoted}", timeout=15)
    if rc != 0:
        lowered = stderr.lower() + stdout.lower()
        if "permission denied" in lowered:
            return {"ok": False, "error": "permission_denied"}
        if "no such file" in lowered:
            return {"ok": False, "error": "not_found"}
        return {"ok": False, "error": "unknown", "detail": (stderr or stdout).strip()[:300]}

    entries = []
    all_parseable = True
    for line in stdout.splitlines():
        parsed = _parse_ls_line(line)
        if parsed is None:
            continue
        if not parsed.get("parseable", True):
            all_parseable = False
        entries.append(parsed)
    entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))

    normalized = remote_path.rstrip("/") or "/"
    parts = [p for p in normalized.split("/") if p]
    breadcrumbs = [{"name": "/", "path": "/"}]
    acc = ""
    for part in parts:
        acc += f"/{part}"
        breadcrumbs.append({"name": part, "path": acc})

    return {"ok": True, "path": normalized, "breadcrumbs": breadcrumbs, "entries": entries, "parseable": all_parseable}


def search_path(serial: str, root: str, query: str, max_results: int = 300) -> dict:
    quoted_root = manager.quote_remote(root)
    quoted_query = manager.quote_remote(f"*{query}*")
    cmd = f"find {quoted_root} -iname {quoted_query} 2>/dev/null | head -n {int(max_results)}"
    stdout, _stderr, rc = manager.shell(serial, cmd, timeout=30)
    if rc not in (0, 1):  # find returns 1 on partial permission errors even with results
        return {"ok": False, "error": "search_failed"}
    paths = [p for p in stdout.splitlines() if p.strip()]
    return {"ok": True, "results": paths, "truncated": len(paths) >= max_results}


def mkdir_path(serial: str, remote_path: str) -> dict:
    _stdout, stderr, rc = manager.shell(serial, f"mkdir -p {manager.quote_remote(remote_path)}", timeout=10)
    return {"ok": rc == 0, "error": None if rc == 0 else stderr.strip()[:300]}


def delete_path(serial: str, remote_path: str, recursive: bool = False) -> dict:
    flag = "-rf" if recursive else "-f"
    _stdout, stderr, rc = manager.shell(serial, f"rm {flag} {manager.quote_remote(remote_path)}", timeout=30)
    return {"ok": rc == 0, "error": None if rc == 0 else stderr.strip()[:300]}


def move_path(serial: str, src: str, dest: str) -> dict:
    _stdout, stderr, rc = manager.shell(
        serial, f"mv {manager.quote_remote(src)} {manager.quote_remote(dest)}", timeout=30
    )
    return {"ok": rc == 0, "error": None if rc == 0 else stderr.strip()[:300]}


def copy_path(serial: str, src: str, dest: str) -> dict:
    _stdout, stderr, rc = manager.shell(
        serial, f"cp -r {manager.quote_remote(src)} {manager.quote_remote(dest)}", timeout=60
    )
    return {"ok": rc == 0, "error": None if rc == 0 else stderr.strip()[:300]}


def rename_path(serial: str, remote_path: str, new_name: str) -> dict:
    if "/" in new_name or new_name in (".", ".."):
        return {"ok": False, "error": "invalid_name"}
    parent = remote_path.rsplit("/", 1)[0] or "/"
    dest = f"{parent.rstrip('/')}/{new_name}"
    return move_path(serial, remote_path, dest)


def pull_file(serial: str, remote_path: str, local_dir: Path) -> Path:
    manager.validate_serial(serial)
    local_dir.mkdir(parents=True, exist_ok=True)
    proc = manager.run(["-s", serial, "pull", remote_path, str(local_dir)], timeout=300)
    if proc.returncode != 0:
        raise manager.AdbError(f"pull failed: {proc.stderr.strip()[:300]}")
    name = remote_path.rstrip("/").rsplit("/", 1)[-1]
    result = local_dir / name
    if not result.exists():
        candidates = list(local_dir.iterdir())
        if len(candidates) == 1:
            return candidates[0]
        raise manager.AdbError("pulled file not found in destination directory")
    return result


def pull_folder(serial: str, remote_path: str, local_dir: Path) -> Path:
    return pull_file(serial, remote_path, local_dir)


def zip_folder(src_dir: Path, zip_base_path: Path) -> Path:
    archive = shutil.make_archive(str(zip_base_path), "zip", root_dir=str(src_dir))
    return Path(archive)


def push_file(serial: str, local_path: Path, remote_dir: str) -> dict:
    manager.validate_serial(serial)
    remote_target = f"{remote_dir.rstrip('/')}/{local_path.name}"
    proc = manager.run(["-s", serial, "push", str(local_path), remote_target], timeout=300)
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr.strip()[:300]}
    return {"ok": True, "remote_path": remote_target}


def preview_kind(remote_path: str) -> str:
    ext = Path(remote_path).suffix.lower()
    if ext in PREVIEWABLE_IMAGE_EXT:
        return "image"
    if ext in PREVIEWABLE_TEXT_EXT:
        return "text"
    return "unsupported"


def read_text_preview(serial: str, remote_path: str, max_bytes: int = 300_000) -> dict:
    quoted = manager.quote_remote(remote_path)
    stdout, stderr, rc = manager.shell(serial, f"head -c {max_bytes} {quoted}", timeout=15)
    if rc != 0:
        return {"ok": False, "error": stderr.strip()[:300] or "read_failed"}
    return {"ok": True, "content": stdout, "truncated": len(stdout.encode("utf-8", "replace")) >= max_bytes}


def with_temp_dir():
    return tempfile.TemporaryDirectory()
