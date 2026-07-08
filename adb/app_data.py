"""Per-app private/public data explorer: browse, read, edit, and delete an
app's data directory (databases, shared_prefs, files, cache) plus its public
external-storage directory, with run-as/root awareness like app_inspector.

Two scopes:
  private - /data/data/<package> (needs run-as on a debuggable app, or root)
  public  - /sdcard/Android/data/<package> (usually shell-readable directly)

Binary transfer safety: adb shell is a text pipe, so anything that isn't
guaranteed-text (a SQLite DB, an arbitrary file) is base64-encoded on-device
and decoded here rather than read raw -- the same reasoning as
adb/files.py's approach, just routed through run-as/su instead of `adb pull`
(which cannot reach another app's private uid-owned files at all).
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import sqlite3
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from . import files as files_mod
from . import manager, packages

_TEXT_EXTENSIONS = {".txt", ".xml", ".json", ".log", ".properties", ".ini", ".conf", ".csv", ".yaml", ".yml"}
_DB_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}
_SHARED_PREF_VALUE_TYPES = ("string", "boolean", "int", "long", "float")
_MAX_EDIT_BYTES = 512 * 1024
_MAX_DB_PULL_BYTES = 200 * 1024 * 1024


def _scope_base(package: str, scope: str) -> str:
    if scope == "private":
        return f"/data/data/{package}"
    if scope == "public":
        return f"/sdcard/Android/data/{package}"
    raise manager.AdbError(f"invalid scope: {scope!r} (expected 'private' or 'public')")


def _validate_relative_path(relative_path: str) -> str:
    """Reject absolute paths and `..` traversal for a path relative to a
    scope base dir. Returns "" for the base dir itself (empty/"." input)."""
    relative_path = (relative_path or "").strip()
    if relative_path in ("", "."):
        return ""
    if relative_path.startswith("/") or any(part == ".." for part in relative_path.split("/")):
        raise manager.AdbError("invalid path: absolute paths and '..' are not allowed")
    return relative_path.strip("/")


def _target_path(package: str, scope: str, relative_path: str) -> tuple[str, str]:
    """Returns (validated relative path, full remote path) for scope/relative_path."""
    rel = _validate_relative_path(relative_path)
    base = _scope_base(package, scope)
    return rel, (f"{base}/{rel}" if rel else base)


def _run_as_or_root(serial: str, package: str, cmd_suffix: str, timeout: int = 15) -> tuple[str, int]:
    """Run cmd_suffix as the app's uid via `run-as` (works on debuggable
    apps), falling back to `su -c` on rooted devices. cmd_suffix is quoted as
    a single opaque string for the su fallback -- NOT re-wrapped in manual
    quotes -- so it's safe even when it already contains shell-quoted
    fragments (e.g. from manager.quote_remote())."""
    stdout, _stderr, rc = manager.shell(serial, f"run-as {manager.quote_remote(package)} {cmd_suffix}", timeout=timeout)
    if rc == 0:
        return stdout, rc
    if manager.has_root_shell(serial):
        stdout, _stderr, rc = manager.shell(serial, f"su -c {manager.quote_remote(cmd_suffix)}", timeout=timeout)
        return stdout, rc
    return "", rc


def _read_bytes(serial: str, package: str, scope: str, target: str, max_bytes: int) -> bytes | None:
    cmd = f"head -c {int(max_bytes)} {manager.quote_remote(target)} 2>/dev/null | base64"
    if scope == "private":
        stdout, rc = _run_as_or_root(serial, package, cmd, timeout=30)
    else:
        stdout, _stderr, rc = manager.shell(serial, cmd, timeout=30)
    if rc != 0 or not stdout.strip():
        return None
    try:
        return base64.b64decode(stdout, validate=False)
    except (binascii.Error, ValueError):
        return None


def _write_bytes(serial: str, package: str, scope: str, target: str, data: bytes) -> tuple[bool, str | None]:
    if len(data) > _MAX_EDIT_BYTES:
        return False, "content too large to edit in place (512KB limit)"
    encoded = base64.b64encode(data).decode("ascii")
    write_cmd = f"echo {manager.quote_remote(encoded)} | base64 -d > {manager.quote_remote(target)}"
    if scope == "private":
        _stdout, rc = _run_as_or_root(serial, package, write_cmd, timeout=30)
    else:
        _stdout, _stderr, rc = manager.shell(serial, write_cmd, timeout=30)
    return rc == 0, None if rc == 0 else "write_failed (requires run-as/root access)"


def _looks_like_text(raw: bytes) -> bool:
    if not raw:
        return True
    sample = raw[:4096]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _list_dir(serial: str, package: str, scope: str, target: str) -> tuple[list[dict] | None, str | None]:
    cmd = f"ls -la {manager.quote_remote(target)} 2>/dev/null"
    if scope == "private":
        stdout, rc = _run_as_or_root(serial, package, cmd)
    else:
        stdout, _stderr, rc = manager.shell(serial, cmd, timeout=15)
    if rc != 0 or not stdout.strip():
        return None, "not_found_or_inaccessible"
    entries = []
    for line in stdout.splitlines():
        parsed = files_mod._parse_ls_line(line)
        if parsed:
            entries.append(parsed)
    entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
    return entries, None


def list_data(serial: str, package: str, scope: str = "private", path: str = "") -> dict:
    packages.validate_package(package)
    rel, target = _target_path(package, scope, path)
    entries, error = _list_dir(serial, package, scope, target)
    if error:
        return {
            "ok": False, "scope": scope, "path": rel, "accessible": False, "error": error,
            "limitation": None if scope == "public" else (
                "Private app data is not accessible: requires the app to be debuggable (for run-as) or a rooted device."
            ),
        }
    return {"ok": True, "scope": scope, "path": rel, "accessible": True, "entries": entries}


def get_data_overview(serial: str, package: str) -> dict:
    packages.validate_package(package)
    return {
        "package": package,
        "private": list_data(serial, package, scope="private", path=""),
        "public": list_data(serial, package, scope="public", path=""),
    }


def _parse_shared_prefs(xml_text: str) -> list[dict] | None:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    if root.tag != "map":
        return None
    entries = []
    for el in root:
        if el.tag == "string":
            value = el.text or ""
        elif el.tag == "set":
            value = [child.text for child in el if child.tag == "string"]
        else:
            value = el.get("value")
        entries.append({"key": el.get("name"), "type": el.tag, "value": value})
    return entries


def read_data_file(serial: str, package: str, relative_path: str, scope: str = "private", max_bytes: int = 300_000) -> dict:
    packages.validate_package(package)
    rel, target = _target_path(package, scope, relative_path)
    if not rel:
        raise manager.AdbError("missing path")
    ext = Path(rel).suffix.lower()

    if ext in _DB_EXTENSIONS:
        return {"ok": True, "kind": "database", "path": rel, "scope": scope,
                "note": "Use the databases endpoint to list tables and run SELECT queries against this file."}

    raw = _read_bytes(serial, package, scope, target, max_bytes)
    if raw is None:
        return {"ok": False, "error": "read_failed_or_inaccessible", "path": rel, "scope": scope}

    if ext in _TEXT_EXTENSIONS or _looks_like_text(raw):
        text = raw.decode("utf-8", errors="replace")
        parsed = None
        kind = "text"
        if ext == ".xml" and "shared_prefs" in rel:
            parsed = _parse_shared_prefs(text)
            kind = "shared_prefs" if parsed is not None else "text"
        elif ext == ".json":
            try:
                parsed = json.loads(text)
                kind = "json"
            except json.JSONDecodeError:
                parsed = None
        return {"ok": True, "kind": kind, "path": rel, "scope": scope, "content": text,
                "truncated": len(raw) >= max_bytes, "parsed": parsed}

    return {"ok": True, "kind": "binary", "path": rel, "scope": scope,
            "size": len(raw), "truncated": len(raw) >= max_bytes, "base64": base64.b64encode(raw).decode("ascii")}


def edit_file(serial: str, package: str, relative_path: str, content: str, scope: str = "private") -> dict:
    packages.validate_package(package)
    rel, target = _target_path(package, scope, relative_path)
    if not rel:
        raise manager.AdbError("missing path")
    ok, error = _write_bytes(serial, package, scope, target, content.encode("utf-8"))
    if not ok:
        raise manager.AdbError(error)
    return {"ok": True, "path": rel, "scope": scope}


def edit_shared_pref_entry(
    serial: str, package: str, relative_path: str, key: str, value, value_type: str = "string", scope: str = "private",
) -> dict:
    """Read a shared_prefs XML file, update/insert one <key,value> entry
    (dropping any existing entry for that key first, since Android's own
    writer never emits duplicate `name` attributes), and write it back."""
    packages.validate_package(package)
    rel, target = _target_path(package, scope, relative_path)
    if not rel:
        raise manager.AdbError("missing path")
    if not key:
        raise manager.AdbError("missing key")
    if value_type not in _SHARED_PREF_VALUE_TYPES:
        raise manager.AdbError(f"unsupported shared-pref value type: {value_type!r}")

    current = read_data_file(serial, package, rel, scope=scope)
    if not current.get("ok"):
        raise manager.AdbError(current.get("error") or "could not read shared_prefs file")
    try:
        root = ET.fromstring(current["content"])
    except ET.ParseError as exc:
        raise manager.AdbError(f"could not parse shared_prefs XML: {exc}") from exc
    if root.tag != "map":
        raise manager.AdbError("not a SharedPreferences XML file")

    existing = next((el for el in root if el.get("name") == key), None)
    if existing is not None:
        root.remove(existing)
    new_el = ET.SubElement(root, value_type)
    new_el.set("name", key)
    if value_type == "string":
        new_el.text = "" if value is None else str(value)
    else:
        new_el.set("value", str(value))

    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    ok, error = _write_bytes(serial, package, scope, target, xml_bytes)
    if not ok:
        raise manager.AdbError(error)
    return {"ok": True, "path": rel, "scope": scope, "key": key}


def delete_data(serial: str, package: str, relative_paths: list[str], scope: str = "private") -> dict:
    packages.validate_package(package)
    if not relative_paths:
        raise manager.AdbError("no paths provided")
    results = []
    for raw_path in relative_paths:
        try:
            rel, target = _target_path(package, scope, raw_path)
        except manager.AdbError:
            results.append({"path": raw_path, "ok": False, "error": "invalid_path"})
            continue
        if not rel:
            # Empty/"." resolves to the scope base dir itself -- refuse to
            # wipe an app's entire data directory from a "delete these files" call.
            results.append({"path": raw_path, "ok": False, "error": "invalid_path"})
            continue
        cmd = f"rm -rf {manager.quote_remote(target)}"
        if scope == "private":
            _stdout, rc = _run_as_or_root(serial, package, cmd)
        else:
            _stdout, _stderr, rc = manager.shell(serial, cmd, timeout=30)
        results.append({"path": rel, "ok": rc == 0})
    return {"ok": all(r["ok"] for r in results), "results": results}


def list_databases(serial: str, package: str) -> dict:
    target = f"{_scope_base(package, 'private')}/databases"
    entries, error = _list_dir(serial, package, "private", target)
    if error:
        return {"ok": False, "accessible": False, "databases": [],
                "limitation": "Private app data is not accessible: requires the app to be debuggable (for run-as) or a rooted device."}
    names = [e["name"] for e in entries if e["type"] == "file" and Path(e["name"]).suffix.lower() in _DB_EXTENSIONS]
    return {"ok": True, "accessible": True, "databases": sorted(names)}


def query_database(serial: str, package: str, db_name: str, query: str | None = None, max_rows: int = 200) -> dict:
    packages.validate_package(package)
    if not db_name or "/" in db_name or db_name in (".", ".."):
        raise manager.AdbError("invalid database name")
    target = f"{_scope_base(package, 'private')}/databases/{db_name}"
    raw = _read_bytes(serial, package, "private", target, _MAX_DB_PULL_BYTES)
    if raw is None:
        raise manager.AdbError("database not accessible (requires run-as/root)")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "preview.db"
        db_path.write_bytes(raw)
        # mode=ro: defense in depth on top of the SELECT-only gate below --
        # even a regex bypass can't turn this into a write against the copy,
        # let alone the on-device original (this is a local temp copy only).
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [r[0] for r in cur.fetchall()]

            columns, rows = [], []
            if query:
                stripped = query.strip().rstrip(";")
                if not re.match(r"(?is)^select\b", stripped):
                    raise manager.AdbError("only SELECT queries are allowed")
                try:
                    cur.execute(f"{stripped} LIMIT {int(max_rows)}")
                except sqlite3.Error as exc:
                    raise manager.AdbError(f"query failed: {exc}") from exc
                columns = [d[0] for d in cur.description] if cur.description else []
                rows = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    return {"ok": True, "database": db_name, "tables": tables, "columns": columns, "rows": rows}
