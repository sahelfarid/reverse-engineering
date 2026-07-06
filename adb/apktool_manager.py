"""Local apktool workflow: install, decompile, browse/edit, rebuild, sign."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests

import config
from . import jobs, manager, packages

APKTOOL_JAR = config.VENDOR_DIR / "apktool" / "apktool.jar"
DEBUG_KEYSTORE = config.VENDOR_DIR / "debug.keystore"
PROJECTS_DIR = config.WORKSPACE_DIR / "apktool_projects"
BUILDS_DIR = config.WORKSPACE_DIR / "apktool_builds"
SOURCES_DIR = config.WORKSPACE_DIR / "apktool_sources"

_PROJECT_RE = re.compile(r"^[A-Za-z0-9_.-]{1,180}$")
_TEXT_EXTENSIONS = {
    ".smali", ".xml", ".txt", ".json", ".yml", ".yaml", ".properties", ".mf",
    ".cfg", ".conf", ".ini", ".gradle", ".java", ".kt", ".html", ".css", ".js",
}


class ApktoolError(manager.AdbError):
    pass


def _run_tool(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ApktoolError(f"tool command failed: {args[0]}") from exc


def _tool_version(path: str, args: list[str], timeout: int = 10) -> str | None:
    proc = _run_tool([path, *args], timeout=timeout)
    if proc.returncode != 0:
        return None
    text = (proc.stdout or proc.stderr or "").strip()
    return text.splitlines()[0] if text else None


def java_status() -> dict:
    java = shutil.which("java")
    if not java:
        return {
            "installed": False,
            "path": None,
            "version": None,
            "message": "Java Runtime required for apktool: https://adoptium.net/",
        }
    version = _tool_version(java, ["-version"])
    return {"installed": bool(version), "path": java, "version": version, "message": None}


def apktool_version() -> str | None:
    if not APKTOOL_JAR.is_file() or not shutil.which("java"):
        return None
    proc = _run_tool([shutil.which("java"), "-jar", str(APKTOOL_JAR), "--version"], timeout=15)
    return proc.stdout.strip() if proc.returncode == 0 else None


def _sdk_roots() -> list[Path]:
    settings = config.load_settings()
    roots = [
        settings.get("android_sdk_path_override"),
        os.environ.get("ANDROID_HOME"),
        os.environ.get("ANDROID_SDK_ROOT"),
    ]
    seen, result = set(), []
    for root in roots:
        if not root:
            continue
        path = Path(root).expanduser()
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def _build_tool_name(name: str) -> str:
    if os.name != "nt":
        return name
    if name == "zipalign":
        return "zipalign.exe"
    return f"{name}.bat"


def _find_in_build_tools(name: str) -> str | None:
    exe = _build_tool_name(name)
    for root in _sdk_roots():
        build_tools = root / "build-tools"
        if not build_tools.is_dir():
            continue
        for version_dir in sorted(build_tools.iterdir(), reverse=True):
            candidate = version_dir / exe
            if candidate.is_file():
                return str(candidate)
    return shutil.which(exe) or shutil.which(name)


def signing_tools_status() -> dict:
    apksigner = _find_in_build_tools("apksigner")
    zipalign = _find_in_build_tools("zipalign")
    jarsigner = shutil.which("jarsigner")
    keytool = shutil.which("keytool")
    return {
        "apksigner": apksigner,
        "zipalign": zipalign,
        "jarsigner": jarsigner,
        "keytool": keytool,
        "available": bool(apksigner or jarsigner),
        "preferred": "apksigner" if apksigner else ("jarsigner" if jarsigner else None),
    }


def get_status() -> dict:
    java = java_status()
    return {
        "ok": True,
        "java": java,
        "apktool": {
            "installed": APKTOOL_JAR.is_file(),
            "version": apktool_version(),
            "path": str(APKTOOL_JAR) if APKTOOL_JAR.is_file() else None,
            "pinned_version": config.APKTOOL_VERSION,
        },
        "signing": signing_tools_status(),
        "debug_keystore": {
            "present": DEBUG_KEYSTORE.is_file(),
            "path": str(DEBUG_KEYSTORE),
        },
    }


def ensure_apktool(chunk_size: int = 1 << 16) -> Path:
    if APKTOOL_JAR.is_file():
        return APKTOOL_JAR
    url = config.APKTOOL_URL_TEMPLATE.format(version=config.APKTOOL_VERSION)
    tmp = config.TEMP_DIR / f"apktool_{config.APKTOOL_VERSION}.jar"
    APKTOOL_JAR.parent.mkdir(parents=True, exist_ok=True)
    try:
        with requests.get(url, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        fh.write(chunk)
        tmp.replace(APKTOOL_JAR)
    except requests.RequestException as exc:
        raise ApktoolError(f"Failed to download apktool: {exc}") from exc
    finally:
        if tmp.exists():
            tmp.unlink()
    return APKTOOL_JAR


def validate_project(project: str) -> str:
    project = str(project or "").strip()
    if not _PROJECT_RE.match(project) or ".." in project:
        raise ApktoolError("invalid project name")
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
        raise ApktoolError("invalid project path")
    target = (root / raw).resolve()
    if target != root and not _is_relative_to(target, root):
        raise ApktoolError("project path escapes project root")
    return target


def _project_meta(root: Path) -> dict:
    marker = root / ".apktool-panel"
    if marker.is_file():
        try:
            text = marker.read_text(encoding="utf-8").splitlines()
            return dict(line.split("=", 1) for line in text if "=" in line)
        except OSError:
            return {}
    return {}


def _write_project_meta(root: Path, package: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".apktool-panel").write_text(
        f"package={package}\ndecompiled_at={int(time.time())}\n", encoding="utf-8",
    )


def _dir_size(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            try:
                total += path.stat().st_size
            except OSError:
                pass
    return total


def decompile(serial: str, package: str, job_id: str | None = None) -> Path:
    packages.validate_package(package)
    java = java_status()
    if not java["installed"]:
        raise ApktoolError(java["message"])
    jar = ensure_apktool()
    root = project_dir(package)
    source_dir = SOURCES_DIR / package
    if job_id:
        jobs.update_job(job_id, progress=5, message="Pulling APK from device")
    source_apk = packages.pull_apk(serial, package, source_dir)
    if job_id:
        jobs.update_job(job_id, progress=35, message="Decompiling with apktool")
    root.parent.mkdir(parents=True, exist_ok=True)
    proc = _run_tool([java["path"], "-jar", str(jar), "d", str(source_apk), "-o", str(root), "-f"], timeout=900)
    if proc.returncode != 0:
        raise ApktoolError((proc.stderr or proc.stdout or "apktool decompile failed").strip()[:1000])
    _write_project_meta(root, package)
    if job_id:
        jobs.update_job(job_id, progress=95, message="Decompile complete")
    return root


def list_projects() -> list[dict]:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    for root in sorted((p for p in PROJECTS_DIR.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
        if not _PROJECT_RE.match(root.name):
            continue
        meta = _project_meta(root)
        try:
            stat = root.stat()
        except OSError:
            continue
        result.append({
            "project": root.name,
            "package": meta.get("package") or root.name,
            "decompiled_at": int(meta.get("decompiled_at") or stat.st_mtime),
            "size": _dir_size(root),
        })
    return result


def browse_project(project: str, relative_path: str = "") -> dict:
    root = project_dir(project).resolve()
    target = resolve_project_path(project, relative_path)
    if not target.exists() or not target.is_dir():
        raise ApktoolError("project path not found")
    entries = []
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        resolved = child.resolve()
        if not _is_relative_to(resolved, root):
            continue
        stat = child.stat()
        entries.append({
            "name": child.name,
            "type": "dir" if child.is_dir() else "file",
            "size": stat.st_size if child.is_file() else None,
            "modified": int(stat.st_mtime),
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
    target = resolve_project_path(project, relative_path)
    if not target.is_file():
        raise ApktoolError("project file not found")
    if target.suffix.lower() not in _TEXT_EXTENSIONS and target.stat().st_size > 1024 * 1024:
        raise ApktoolError("file is too large or not a supported text file")
    return target.read_text(encoding="utf-8", errors="replace")


def write_project_file(project: str, relative_path: str, content: str) -> dict:
    target = resolve_project_path(project, relative_path)
    if not target.exists() or not target.is_file():
        raise ApktoolError("project file not found")
    if len(str(content).encode("utf-8")) > 2 * 1024 * 1024:
        raise ApktoolError("file content too large")
    target.write_text(str(content), encoding="utf-8")
    return {"ok": True, "path": relative_path}


def ensure_debug_keystore() -> Path:
    if DEBUG_KEYSTORE.is_file():
        return DEBUG_KEYSTORE
    keytool = signing_tools_status()["keytool"]
    if not keytool:
        raise ApktoolError("keytool is required to generate the debug signing keystore")
    DEBUG_KEYSTORE.parent.mkdir(parents=True, exist_ok=True)
    proc = _run_tool([
        keytool, "-genkeypair", "-v",
        "-keystore", str(DEBUG_KEYSTORE),
        "-alias", "androiddebugkey",
        "-keyalg", "RSA",
        "-keysize", "2048",
        "-validity", "10000",
        "-storepass", "android",
        "-keypass", "android",
        "-dname", "CN=Android Debug,O=Android,C=US",
        "-noprompt",
    ], timeout=60)
    if proc.returncode != 0:
        raise ApktoolError((proc.stderr or proc.stdout or "debug keystore generation failed").strip()[:1000])
    return DEBUG_KEYSTORE


def _zipalign(unsigned_apk: Path, tools: dict) -> tuple[Path, bool]:
    zipalign = tools.get("zipalign")
    if not zipalign:
        return unsigned_apk, False
    aligned = unsigned_apk.with_name("rebuilt-aligned.apk")
    proc = _run_tool([zipalign, "-f", "4", str(unsigned_apk), str(aligned)], timeout=120)
    return (aligned, True) if proc.returncode == 0 and aligned.is_file() else (unsigned_apk, False)


def _sign_apk(input_apk: Path, signed_apk: Path, tools: dict) -> str:
    keystore = ensure_debug_keystore()
    if tools.get("apksigner"):
        proc = _run_tool([
            tools["apksigner"], "sign",
            "--ks", str(keystore),
            "--ks-key-alias", "androiddebugkey",
            "--ks-pass", "pass:android",
            "--key-pass", "pass:android",
            "--out", str(signed_apk),
            str(input_apk),
        ], timeout=180)
        if proc.returncode != 0:
            raise ApktoolError((proc.stderr or proc.stdout or "apksigner failed").strip()[:1000])
        return "apksigner"
    if tools.get("jarsigner"):
        proc = _run_tool([
            tools["jarsigner"],
            "-keystore", str(keystore),
            "-storepass", "android",
            "-keypass", "android",
            "-signedjar", str(signed_apk),
            str(input_apk),
            "androiddebugkey",
        ], timeout=180)
        if proc.returncode != 0:
            raise ApktoolError((proc.stderr or proc.stdout or "jarsigner failed").strip()[:1000])
        return "jarsigner"
    raise ApktoolError("No APK signing tool found. Install Android SDK build-tools for apksigner, or a JDK for jarsigner.")


def rebuild(project: str, job_id: str | None = None) -> Path:
    java = java_status()
    if not java["installed"]:
        raise ApktoolError(java["message"])
    jar = ensure_apktool()
    root = project_dir(project)
    if not root.is_dir():
        raise ApktoolError("project not found")
    out_dir = BUILDS_DIR / validate_project(project)
    out_dir.mkdir(parents=True, exist_ok=True)
    unsigned_apk = out_dir / "rebuilt-unsigned.apk"
    signed_apk = out_dir / "rebuilt-signed.apk"
    if job_id:
        jobs.update_job(job_id, progress=10, message="Rebuilding APK")
    proc = _run_tool([java["path"], "-jar", str(jar), "b", str(root), "-o", str(unsigned_apk)], timeout=900)
    if proc.returncode != 0:
        raise ApktoolError((proc.stderr or proc.stdout or "apktool rebuild failed").strip()[:1000])
    tools = signing_tools_status()
    input_apk, aligned = _zipalign(unsigned_apk, tools)
    if job_id:
        jobs.update_job(job_id, progress=80, message="Signing APK")
    signer = _sign_apk(input_apk, signed_apk, tools)
    if job_id:
        jobs.update_job(job_id, progress=95, message=f"Signed with {signer}" + (", zipaligned" if aligned else ""))
    return signed_apk


def reinstall(serial: str, signed_apk_path: str | Path) -> dict:
    path = Path(signed_apk_path)
    builds = BUILDS_DIR.resolve()
    resolved = path.resolve()
    if not path.is_file() or not _is_relative_to(resolved, builds):
        raise ApktoolError("signed APK not found")
    return packages.install_apk(serial, resolved)


def delete_project(project: str) -> dict:
    root = project_dir(project)
    if not root.is_dir():
        raise ApktoolError("project not found")
    shutil.rmtree(root)
    return {"ok": True}
