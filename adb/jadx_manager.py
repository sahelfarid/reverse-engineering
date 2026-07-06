"""Local jadx workflow: install, decompile (device pull or local upload),
browse/read/search decompiled sources, manifest summary, static findings, and
report export.

Unlike the apktool module this is read-only end to end: jadx only goes
dex -> Java, there is no rebuild/sign/reinstall here (that stays in
adb/apktool_manager.py), and nothing this module produces is ever executed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import requests
from werkzeug.utils import secure_filename

import config
from . import apktool_manager, jobs, manager, packages

JADX_DIR = config.VENDOR_DIR / "jadx"
PROJECTS_DIR = config.WORKSPACE_DIR / "jadx_projects"
SOURCES_DIR = config.WORKSPACE_DIR / "jadx_sources"
FINDINGS_DIR = config.WORKSPACE_DIR / "jadx_findings"
REPORTS_DIR = config.WORKSPACE_DIR / "jadx_reports"

_PROJECT_RE = re.compile(r"^[A-Za-z0-9_.-]{1,180}$")
_TEXT_EXTENSIONS = {
    ".java", ".smali", ".xml", ".txt", ".json", ".properties", ".kt", ".gradle",
    ".yml", ".yaml", ".cfg", ".conf", ".ini", ".mf", ".html", ".css", ".js",
}
_ALLOWED_IMPORT_EXTENSIONS = {".apk", ".dex", ".jar"}
_MAX_SEARCH_FILE_BYTES = 2 * 1024 * 1024
_MAX_SCANNED_FILES = 20_000
_MAX_SEARCH_SECONDS = 20
_ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
_MANIFEST_CANDIDATES = ("AndroidManifest.xml", "resources/AndroidManifest.xml")


class JadxError(manager.AdbError):
    pass


# --- tool discovery / install -----------------------------------------------

def java_status() -> dict:
    return apktool_manager.java_status()


def _launcher_name() -> str:
    return "jadx.bat" if os.name == "nt" else "jadx"


def _vendor_launcher_path() -> Path:
    return JADX_DIR / "bin" / _launcher_name()


def _jadx_path_override() -> str | None:
    return config.load_settings().get("jadx_path_override")


def find_jadx() -> Path | None:
    """Resolution order: explicit settings override, then PATH, then the
    app-managed vendor/jadx/ install -- matches adb.manager.find_adb()'s
    override-then-PATH-then-vendor shape."""
    override = _jadx_path_override()
    if override and Path(override).is_file():
        return Path(override)
    system_jadx = shutil.which("jadx")
    if system_jadx:
        return Path(system_jadx)
    vendor = _vendor_launcher_path()
    if vendor.is_file():
        return vendor
    return None


def _tool_source(path: Path) -> str:
    override = _jadx_path_override()
    if override and Path(override).resolve() == path.resolve():
        return "override"
    if str(path).startswith(str(JADX_DIR)):
        return "vendor"
    return "system"


def jadx_version(path: Path | None = None) -> str | None:
    launcher = path or find_jadx()
    if not launcher:
        return None
    try:
        proc = subprocess.run([str(launcher), "--version"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    text = (proc.stdout or proc.stderr or "").strip()
    return text.splitlines()[0] if text else None


def get_status() -> dict:
    java = java_status()
    launcher = find_jadx()
    return {
        "ok": True,
        "java": java,
        "jadx": {
            "installed": launcher is not None,
            "version": jadx_version(launcher) if launcher else None,
            "path": str(launcher) if launcher else None,
            "source": _tool_source(launcher) if launcher else None,
            "pinned_version": config.JADX_VERSION,
        },
    }


def ensure_jadx() -> Path:
    """Return a usable jadx launcher, downloading+extracting the pinned
    release into vendor/jadx/ only if no override/PATH/vendor install already
    resolves (mirrors adb.manager.install_adb's download-to-temp -> extract ->
    chmod flow, but skips the download entirely when jadx is already
    available)."""
    existing = find_jadx()
    if existing:
        return existing
    url = config.JADX_URL_TEMPLATE.format(version=config.JADX_VERSION)
    zip_path = config.TEMP_DIR / f"jadx_{config.JADX_VERSION}.zip"
    JADX_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with requests.get(url, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(zip_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    if chunk:
                        fh.write(chunk)
        with zipfile.ZipFile(zip_path) as zf:
            manager._safe_extract(zf, JADX_DIR)
    except requests.RequestException as exc:
        raise JadxError(f"Failed to download jadx: {exc}") from exc
    except zipfile.BadZipFile as exc:
        raise JadxError(f"Downloaded file is not a valid zip: {exc}") from exc
    except manager.AdbInstallError as exc:
        raise JadxError(str(exc)) from exc
    finally:
        if zip_path.exists():
            zip_path.unlink()

    launcher = _vendor_launcher_path()
    if not launcher.is_file():
        raise JadxError("jadx launcher not found after extraction")
    if os.name != "nt":
        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return launcher


# --- project path safety (mirrors adb/apktool_manager.py's guards) ---------

def validate_project(project: str) -> str:
    project = str(project or "").strip()
    if not _PROJECT_RE.match(project) or ".." in project:
        raise JadxError("invalid project name")
    return project


def project_dir(project: str) -> Path:
    return PROJECTS_DIR / validate_project(project)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_project_path(project: str, relative_path: str = "") -> Path:
    root = project_dir(project).resolve()
    raw = Path(relative_path or ".")
    if raw.is_absolute() or any(part == ".." for part in raw.parts):
        raise JadxError("invalid project path")
    target = (root / raw).resolve()
    if target != root and not _is_relative_to(target, root):
        raise JadxError("project path escapes project root")
    return target


def _dir_size(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            try:
                total += path.stat().st_size
            except OSError:
                pass
    return total


def _sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _project_meta(root: Path) -> dict:
    marker = root / ".jadx-panel"
    if marker.is_file():
        try:
            lines = marker.read_text(encoding="utf-8").splitlines()
            return dict(line.split("=", 1) for line in lines if "=" in line)
        except OSError:
            return {}
    return {}


def _write_project_meta(root: Path, *, package: str, sha256: str, source: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".jadx-panel").write_text(
        f"package={package}\ndecompiled_at={int(time.time())}\nsha256={sha256}\nsource={source}\n",
        encoding="utf-8",
    )


# --- decompile ---------------------------------------------------------------

def _run_jadx_process(job_id: str | None, launcher: Path, args: list[str], timeout: int) -> tuple[int, str]:
    """Runs the jadx launcher with cancellation + timeout support (same shape
    as adb.jobs.run_adb_with_progress, generalized to any binary): polls
    is_cancelled() between output lines, terminates + raises JobCancelled on
    cancel, terminates + raises JadxError on timeout, and keeps only the last
    ~200 output lines in memory so a chatty/obfuscated APK can't exhaust it."""
    process = subprocess.Popen(
        [str(launcher), *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    if job_id:
        jobs.set_job_process(job_id, process)
    start = time.time()
    tail: list[str] = []
    for line in process.stdout:
        if job_id and jobs.is_cancelled(job_id):
            process.terminate()
            raise jobs.JobCancelled()
        if timeout and (time.time() - start) > timeout:
            process.terminate()
            raise JadxError("jadx decompile timed out")
        tail.append(line.rstrip("\n"))
        if len(tail) > 200:
            tail.pop(0)
    process.wait(timeout=10)
    if job_id and jobs.is_cancelled(job_id):
        raise jobs.JobCancelled()
    return process.returncode, "\n".join(tail)


def _run_decompile(
    apk_path: Path, project_root: Path, job_id: str | None, *,
    no_res: bool, deobf: bool, show_bad_code: bool,
) -> str:
    """Core jadx invocation shared by the device-pull and local-upload entry
    points. jadx can exit non-zero on partial per-class decompile failures
    while still producing perfectly usable output, so success is judged by
    "did it write anything", not by exit code alone."""
    java = java_status()
    if not java["installed"]:
        raise JadxError(java["message"])
    launcher = ensure_jadx()
    project_root.parent.mkdir(parents=True, exist_ok=True)
    args = ["-d", str(project_root)]
    if no_res:
        args.append("--no-res")
    if deobf:
        args.append("--deobf")
    if show_bad_code:
        args.append("--show-bad-code")
    args += ["-j", str(os.cpu_count() or 1), str(apk_path)]
    if job_id:
        jobs.update_job(job_id, progress=40, message="Running jadx")
    timeout = int(config.load_settings().get("jadx_decompile_timeout_sec", 600))
    returncode, tail = _run_jadx_process(job_id, launcher, args, timeout)
    has_output = project_root.is_dir() and any(project_root.iterdir())
    if not has_output:
        raise JadxError((tail or "jadx decompile failed").strip()[-1000:])
    if returncode != 0:
        return f"Decompiled with warnings (jadx exit code {returncode})"
    return "Decompiled successfully"


def decompile(
    serial: str, package: str, job_id: str | None = None, *,
    no_res: bool = False, deobf: bool = False, show_bad_code: bool = True,
) -> Path:
    """Device-sourced path: pull the APK off a connected device, then decompile."""
    packages.validate_package(package)
    java = java_status()
    if not java["installed"]:
        raise JadxError(java["message"])
    ensure_jadx()
    source_dir = SOURCES_DIR / package
    project_root = project_dir(package)
    if job_id:
        jobs.update_job(job_id, progress=5, message="Pulling APK from device")
    apk_path = packages.pull_apk(serial, package, source_dir)
    sha256 = _sha256_file(apk_path)
    message = _run_decompile(apk_path, project_root, job_id, no_res=no_res, deobf=deobf, show_bad_code=show_bad_code)
    _write_project_meta(project_root, package=package, sha256=sha256, source="device")
    if job_id:
        jobs.update_job(job_id, progress=95, message=message)
    return project_root


def save_uploaded_artifact(file_storage, display_name: str | None = None) -> tuple[str, Path]:
    """Synchronous half of the local-upload path: validate and persist the
    uploaded file to disk. Deliberately split from decompile_uploaded() below
    so the route can do this part inline (a Flask FileStorage is backed by
    the current request's temp stream and isn't safe to touch once that
    request has torn down) before handing the slow decompile step to a
    background job."""
    filename = secure_filename(file_storage.filename or "")
    ext = Path(filename).suffix.lower()
    if not filename or ext not in _ALLOWED_IMPORT_EXTENSIONS:
        raise JadxError("only .apk, .dex, and .jar files can be imported")
    project = validate_project(display_name) if display_name else f"upload-{uuid.uuid4().hex[:10]}"
    source_dir = SOURCES_DIR / project
    source_dir.mkdir(parents=True, exist_ok=True)
    apk_path = source_dir / filename
    file_storage.save(apk_path)
    return project, apk_path


def decompile_uploaded(
    project: str, apk_path: Path, job_id: str | None = None, *,
    no_res: bool = False, deobf: bool = False, show_bad_code: bool = True,
) -> Path:
    """Decompile an already-saved local upload (see save_uploaded_artifact
    above). Not every target is pulled live off a device -- a lab sample, a
    CTF binary, or a build artifact the operator already has on disk should
    be analyzable too."""
    java = java_status()
    if not java["installed"]:
        raise JadxError(java["message"])
    ensure_jadx()
    sha256 = _sha256_file(apk_path)
    project_root = project_dir(project)
    message = _run_decompile(apk_path, project_root, job_id, no_res=no_res, deobf=deobf, show_bad_code=show_bad_code)
    _write_project_meta(project_root, package=project, sha256=sha256, source="upload")
    if job_id:
        jobs.update_job(job_id, progress=95, message=message)
    return project_root


# --- project listing / browsing / reading / search --------------------------

def list_projects() -> list[dict]:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    for root in sorted((p for p in PROJECTS_DIR.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
        if not _PROJECT_RE.match(root.name):
            continue
        meta = _project_meta(root)
        try:
            stat_ = root.stat()
        except OSError:
            continue
        result.append({
            "project": root.name,
            "package": meta.get("package") or root.name,
            "decompiled_at": int(meta.get("decompiled_at") or stat_.st_mtime),
            "size": _dir_size(root),
            "sha256": meta.get("sha256"),
            "source": meta.get("source", "device"),
        })
    return result


def browse_project(project: str, relative_path: str = "") -> dict:
    root = project_dir(project).resolve()
    target = resolve_project_path(project, relative_path)
    if not target.exists() or not target.is_dir():
        raise JadxError("project path not found")
    entries = []
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        resolved = child.resolve()
        if not _is_relative_to(resolved, root):
            continue
        stat_ = child.stat()
        entries.append({
            "name": child.name,
            "type": "dir" if child.is_dir() else "file",
            "size": stat_.st_size if child.is_file() else None,
            "modified": int(stat_.st_mtime),
        })
    rel = "." if target == root else str(target.relative_to(root))
    breadcrumbs = [{"name": project, "path": ""}]
    parts = [] if rel == "." else Path(rel).parts
    cur = []
    for part in parts:
        cur.append(part)
        breadcrumbs.append({"name": part, "path": "/".join(cur)})
    return {"ok": True, "project": project, "path": "" if rel == "." else rel, "breadcrumbs": breadcrumbs, "entries": entries}


def read_project_file(project: str, relative_path: str) -> str:
    """Read-only by design -- there is deliberately no write_project_file:
    jadx output is not edited or rebuilt."""
    target = resolve_project_path(project, relative_path)
    if not target.is_file():
        raise JadxError("project file not found")
    if target.suffix.lower() not in _TEXT_EXTENSIONS and target.stat().st_size > 1024 * 1024:
        raise JadxError("file is too large or not a supported text file")
    return target.read_text(encoding="utf-8", errors="replace")


def search_project(
    project: str, query: str, *, max_results: int = 200, ignore_case: bool = True, regex: bool = False,
) -> list[dict]:
    root = project_dir(project).resolve()
    if not root.is_dir():
        raise JadxError("project not found")
    if not query:
        return []
    if regex:
        if len(query) > 200:
            raise JadxError("regex query too long")
        try:
            pattern = re.compile(query, re.IGNORECASE if ignore_case else 0)
        except re.error as exc:
            raise JadxError(f"invalid regex: {exc}") from exc
        matcher = pattern.search
    else:
        needle = query.lower() if ignore_case else query

        def matcher(line: str, _needle=needle) -> bool:
            return _needle in (line.lower() if ignore_case else line)

    results: list[dict] = []
    scanned = 0
    start = time.time()
    for path in root.rglob("*"):
        if len(results) >= max_results or scanned >= _MAX_SCANNED_FILES or (time.time() - start) > _MAX_SEARCH_SECONDS:
            break
        if not path.is_file() or path.suffix.lower() not in _TEXT_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > _MAX_SEARCH_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        rel = str(path.relative_to(root))
        for lineno, line in enumerate(text.splitlines(), start=1):
            if matcher(line):
                results.append({"path": rel, "line": lineno, "snippet": line.strip()[:300]})
                if len(results) >= max_results:
                    break
    return results


def delete_project(project: str) -> dict:
    root = project_dir(project)
    if not root.is_dir():
        raise JadxError("project not found")
    shutil.rmtree(root)
    findings_path = FINDINGS_DIR / f"{validate_project(project)}.json"
    if findings_path.is_file():
        findings_path.unlink()
    reports_dir = REPORTS_DIR / validate_project(project)
    if reports_dir.is_dir():
        shutil.rmtree(reports_dir)
    return {"ok": True}


# --- manifest metadata --------------------------------------------------------

def _find_manifest(root: Path) -> Path | None:
    for rel in _MANIFEST_CANDIDATES:
        candidate = root / rel
        if candidate.is_file():
            return candidate
    return None


def _android_attr(el, name: str) -> str | None:
    return el.get(f"{_ANDROID_NS}{name}") if el is not None else None


def manifest_summary(project: str) -> dict:
    """jadx already decompiles the binary AndroidManifest.xml into plain,
    readable XML as part of its normal output -- this just parses the file
    jadx already wrote, no extra AXML-parsing dependency needed."""
    root = project_dir(project)
    if not root.is_dir():
        raise JadxError("project not found")
    manifest_path = _find_manifest(root)
    if not manifest_path:
        raise JadxError("AndroidManifest.xml not found (resources may have been skipped with --no-res)")
    try:
        tree = ET.parse(manifest_path)
    except ET.ParseError as exc:
        raise JadxError(f"failed to parse AndroidManifest.xml: {exc}") from exc
    root_el = tree.getroot()
    app_el = root_el.find("application")
    uses_sdk = root_el.find("uses-sdk")

    def component_list(tag: str) -> list[dict]:
        out = []
        if app_el is None:
            return out
        for el in app_el.findall(tag):
            intents = [
                _android_attr(action, "name")
                for filt in el.findall("intent-filter")
                for action in filt.findall("action")
                if _android_attr(action, "name")
            ]
            out.append({
                "name": _android_attr(el, "name"),
                "exported": _android_attr(el, "exported"),
                "permission": _android_attr(el, "permission"),
                "intent_actions": intents,
            })
        return out

    return {
        "ok": True,
        "package": root_el.get("package"),
        "version_code": _android_attr(root_el, "versionCode"),
        "version_name": _android_attr(root_el, "versionName"),
        "min_sdk": _android_attr(uses_sdk, "minSdkVersion"),
        "target_sdk": _android_attr(uses_sdk, "targetSdkVersion"),
        "debuggable": _android_attr(app_el, "debuggable"),
        "allow_backup": _android_attr(app_el, "allowBackup"),
        "network_security_config": _android_attr(app_el, "networkSecurityConfig"),
        "permissions": [
            _android_attr(el, "name") for el in root_el.findall("uses-permission") if _android_attr(el, "name")
        ],
        "features": [
            _android_attr(el, "name") for el in root_el.findall("uses-feature") if _android_attr(el, "name")
        ],
        "activities": component_list("activity"),
        "services": component_list("service"),
        "receivers": component_list("receiver"),
        "providers": component_list("provider"),
    }


# --- static security checks (opt-in) ------------------------------------------
#
# A lightweight, local, pattern-matching pass over the manifest summary and
# decompiled Java sources. Findings identify risky patterns with evidence for
# an analyst to review -- this never generates exploit steps or bypass code.

_RISKY_PERMISSIONS = {
    "android.permission.SEND_SMS", "android.permission.RECEIVE_SMS", "android.permission.READ_SMS",
    "android.permission.READ_CONTACTS", "android.permission.WRITE_CONTACTS",
    "android.permission.ACCESS_FINE_LOCATION", "android.permission.ACCESS_BACKGROUND_LOCATION",
    "android.permission.RECORD_AUDIO", "android.permission.CAMERA",
    "android.permission.REQUEST_INSTALL_PACKAGES", "android.permission.BIND_ACCESSIBILITY_SERVICE",
    "android.permission.SYSTEM_ALERT_WINDOW", "android.permission.BIND_NOTIFICATION_LISTENER_SERVICE",
    "android.permission.BIND_VPN_SERVICE",
}

_SOURCE_PATTERNS: list[tuple[str, str, "re.Pattern"]] = [
    ("hardcoded-url", "medium", re.compile(r"https?://[^\s\"'<>]+")),
    ("hardcoded-secret", "medium", re.compile(r'(?i)(api[_-]?key|secret|token|password)\s*=\s*"[A-Za-z0-9_\-]{12,}"')),
    ("weak-crypto-des", "high", re.compile(r'"DES(/|")')),
    ("weak-crypto-ecb", "high", re.compile(r"/ECB/")),
    ("weak-hash", "low", re.compile(r'MessageDigest\.getInstance\("(MD5|SHA-1)"\)')),
    ("insecure-random", "low", re.compile(r"\bnew\s+Random\s*\(")),
    ("webview-js-enabled", "low", re.compile(r"\.setJavaScriptEnabled\s*\(\s*true\s*\)")),
    ("webview-file-access", "medium", re.compile(r"\.setAllowFileAccess\s*\(\s*true\s*\)")),
    ("webview-js-interface", "medium", re.compile(r"\.addJavascriptInterface\s*\(")),
    ("tls-permissive-trustmanager", "high", re.compile(r"class\s+\w*TrustManager\b")),
    ("tls-hostname-verifier", "high", re.compile(r"\bHostnameVerifier\b")),
    ("dynamic-code-loading", "medium", re.compile(r"\bDexClassLoader\b|\bPathClassLoader\b")),
    ("insecure-storage-mode", "medium", re.compile(r"MODE_WORLD_READABLE|MODE_WORLD_WRITEABLE")),
]


_COMPONENT_SINGULAR = {
    "activities": "activity", "services": "service", "receivers": "receiver", "providers": "provider",
}


def _manifest_findings(summary: dict) -> list[dict]:
    findings = []
    for kind, singular in _COMPONENT_SINGULAR.items():
        for comp in summary.get(kind, []):
            if comp.get("exported") == "true" and not comp.get("permission") and comp.get("intent_actions"):
                findings.append({
                    "id": f"exported-{singular}-no-permission", "severity": "medium", "confidence": "high",
                    "title": f"Exported {singular} without a permission", "file": "AndroidManifest.xml",
                    "line": None, "snippet": comp.get("name"),
                    "note": "Exported component with no permission attribute is reachable by any app on the device.",
                })
    if summary.get("debuggable") == "true":
        findings.append({
            "id": "debuggable-true", "severity": "medium", "confidence": "high",
            "title": "android:debuggable is true", "file": "AndroidManifest.xml", "line": None, "snippet": None,
            "note": "Debuggable builds allow attaching a debugger or reading process memory.",
        })
    if summary.get("allow_backup") == "true":
        findings.append({
            "id": "allow-backup-true", "severity": "low", "confidence": "high",
            "title": "android:allowBackup is true", "file": "AndroidManifest.xml", "line": None, "snippet": None,
            "note": "App data can be extracted via adb backup on non-hardened devices.",
        })
    for perm in summary.get("permissions", []):
        if perm in _RISKY_PERMISSIONS:
            findings.append({
                "id": "risky-permission", "severity": "low", "confidence": "high",
                "title": f"Requests risky permission {perm}", "file": "AndroidManifest.xml",
                "line": None, "snippet": perm,
                "note": "Review whether this permission is required for the app's stated purpose.",
            })
    return findings


def _source_findings(root: Path) -> list[dict]:
    findings = []
    scanned = 0
    for path in root.rglob("*.java"):
        if scanned >= _MAX_SCANNED_FILES:
            break
        try:
            if path.stat().st_size > _MAX_SEARCH_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        rel = str(path.relative_to(root))
        for lineno, line in enumerate(text.splitlines(), start=1):
            for finding_id, severity, pattern in _SOURCE_PATTERNS:
                if pattern.search(line):
                    findings.append({
                        "id": finding_id, "severity": severity, "confidence": "medium",
                        "title": finding_id.replace("-", " "), "file": rel, "line": lineno,
                        "snippet": line.strip()[:300],
                        "note": "Decompiler-derived match; verify in context before treating as confirmed.",
                    })
    return findings


def run_static_checks(project: str) -> list[dict]:
    root = project_dir(project)
    if not root.is_dir():
        raise JadxError("project not found")
    findings: list[dict] = []
    try:
        findings += _manifest_findings(manifest_summary(project))
    except JadxError:
        pass  # no manifest (e.g. --no-res) -- still run source checks
    findings += _source_findings(root)
    FINDINGS_DIR.mkdir(parents=True, exist_ok=True)
    (FINDINGS_DIR / f"{validate_project(project)}.json").write_text(json.dumps(findings, indent=2), encoding="utf-8")
    return findings


def get_findings(project: str) -> list[dict] | None:
    findings_path = FINDINGS_DIR / f"{validate_project(project)}.json"
    if not findings_path.is_file():
        return None
    try:
        return json.loads(findings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# --- report export -------------------------------------------------------------

_AUTHORIZED_USE_STATEMENT = (
    "Authorized analysis only -- this report covers a device/app the operator "
    "owns or is explicitly authorized to test."
)


def _render_markdown(doc: dict) -> str:
    lines = [
        f"# JADX Analysis Report — {doc['package']}",
        "",
        f"> {doc['authorized_use_statement']}",
        "",
        f"- SHA-256: `{doc['sha256']}`",
        f"- Source: {doc['source']}",
        f"- jadx: {doc['tool_versions'].get('jadx')}  |  Java: {doc['tool_versions'].get('java')}",
        "",
    ]
    manifest = doc.get("manifest")
    if manifest:
        lines += [
            "## Manifest summary", "",
            f"- Package: {manifest.get('package')}",
            f"- Version: {manifest.get('version_name')} ({manifest.get('version_code')})",
            f"- SDK: min {manifest.get('min_sdk')} / target {manifest.get('target_sdk')}",
            f"- Debuggable: {manifest.get('debuggable')}  |  Allow backup: {manifest.get('allow_backup')}",
            "", "### Permissions", "",
        ]
        lines += [f"- {p}" for p in manifest.get("permissions", [])] or ["- (none declared)"]
        lines.append("")
    findings = doc.get("findings") or []
    lines += ["## Findings", ""]
    if not findings:
        lines.append("No static findings recorded for this project.")
    for f in findings:
        loc = f"`{f['file']}`" + (f":{f['line']}" if f.get("line") else "")
        lines.append(f"- **[{f['severity']}]** {f['title']} — {loc}")
    return "\n".join(lines) + "\n"


def export_report(project: str, fmt: str = "json") -> Path:
    root = project_dir(project)
    if not root.is_dir():
        raise JadxError("project not found")
    meta = _project_meta(root)
    status = get_status()
    try:
        manifest = manifest_summary(project)
    except JadxError:
        manifest = None
    doc = {
        "authorized_use_statement": _AUTHORIZED_USE_STATEMENT,
        "project": project,
        "package": meta.get("package", project),
        "sha256": meta.get("sha256"),
        "source": meta.get("source"),
        "decompiled_at": int(meta.get("decompiled_at") or 0) or None,
        "tool_versions": {
            "jadx": status["jadx"].get("version") or status["jadx"].get("pinned_version"),
            "java": status["java"].get("version"),
        },
        "manifest": manifest,
        "findings": get_findings(project) or [],
        "generated_at": int(time.time()),
    }
    reports_dir = REPORTS_DIR / validate_project(project)
    reports_dir.mkdir(parents=True, exist_ok=True)
    if fmt == "md":
        out_path = reports_dir / "report.md"
        out_path.write_text(_render_markdown(doc), encoding="utf-8")
    else:
        out_path = reports_dir / "report.json"
        out_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return out_path
