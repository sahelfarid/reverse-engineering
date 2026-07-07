# JADX

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

APK/DEX/JAR decompilation and static-analysis workflow for authorized reverse-engineering work. The module pulls an installed APK from a connected device (or accepts a local file upload), decompiles it to readable Java with jadx, exposes a local read-only project browser and full-text search, parses the decompiled `AndroidManifest.xml` into a structured summary, runs an opt-in static-findings pass, and exports a JSON/Markdown analysis report.

Unlike the APKTool module, this is a one-directional decompiler: dex -> Java only. There is no rebuild, sign, or reinstall here, and nothing this module produces is ever executed -- that keeps its risk profile lower than APKTool's (no write-back to the device), though the same "apps you own or are explicitly authorized to test" framing still applies to what gets decompiled.

## Files

- `adb/jadx_manager.py`
- `routes/jadx.py`
- `static/js/jadx.js`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/jadx/status` | Java and jadx (override/PATH/vendor) status. |
| POST | `/api/jadx/install` | Download/cache the pinned jadx release. |
| POST | `/api/devices/<serial>/jadx/decompile/<package>` | Start a background decompile job (device-pull path). |
| POST | `/api/jadx/import` | Upload and decompile a local `.apk`/`.dex`/`.jar` (background job). |
| GET | `/api/jadx/projects` | List local decompiled projects. |
| GET | `/api/jadx/projects/<project>/browse?path=...` | Browse a local decompiled project directory. |
| GET | `/api/jadx/projects/<project>/file?path=...` | Read one project text file (read-only; no write route). |
| GET | `/api/jadx/projects/<project>/search?q=...&regex=0` | Full-text search across decompiled sources. |
| GET | `/api/jadx/projects/<project>/manifest` | Parsed `AndroidManifest.xml` summary. |
| GET/POST | `/api/jadx/projects/<project>/findings` | Read the last persisted static-findings result / run the static-findings pass. |
| GET | `/api/jadx/projects/<project>/report?format=json\|md` | Export a JSON or Markdown analysis report. |
| DELETE | `/api/jadx/projects/<project>` | Delete a local project directory (and its findings/report). |

## Behavior

- Java is detected via the shared `adb.apktool_manager.java_status()` check; it is never silently installed.
- jadx resolution order: `jadx_path_override` setting, then `PATH` (`shutil.which("jadx")`), then the app-managed `vendor/jadx/bin/jadx[.bat]` install -- mirrors `adb.manager.find_adb()`'s override-then-PATH-then-vendor shape.
- The managed jadx release is downloaded from the pinned GitHub release and extracted with `adb.manager._safe_extract` (rejects zip-slip members) -- the same helper `install_adb()` uses for the platform-tools zip.
- Decompiled projects live under `workspace/jadx_projects/`; pulled/uploaded source files live under `workspace/jadx_sources/`; persisted findings and report exports live under `workspace/jadx_findings/` and `workspace/jadx_reports/`.
- Decompile runs as a cancellable, timeout-bounded subprocess (`jadx_decompile_timeout_sec` setting, default 600s): the child is registered with the job registry so the existing generic `POST /api/jobs/<id>/cancel` route can terminate it, and only the last ~200 output lines are kept in memory.
- jadx can exit non-zero on partial per-class decompile failures while still producing perfectly usable output. Success is judged by "did the output directory receive any files", not by exit code alone; a non-zero exit with output is reported as "decompiled with warnings", not a failure.
- The local-upload path validates the file extension (`.apk`/`.dex`/`.jar` only) and the existing `max_upload_mb` setting before saving, then decompiles the saved file the same way as the device-pull path.
- Both projects and reads resolve against the project root and reject absolute paths, `..` segments, and symlink escapes -- the same guard shape as `adb/apktool_manager.py`'s project-path safety.
- There is deliberately no file-write route: jadx output is read-only end to end.
- The manifest summary parses the plain, human-readable `AndroidManifest.xml` that jadx already writes as part of decompilation (via the stdlib `xml.etree.ElementTree`) -- no extra AXML-parsing dependency is needed.
- The static-findings pass is opt-in per project (not automatic on every decompile): it combines manifest-derived checks (exported components without a permission, `debuggable`/`allowBackup` flags, risky permissions) with source-derived pattern checks (hardcoded secrets/URLs, weak crypto, risky WebView settings, TLS-bypass patterns, dynamic code loading, insecure storage modes) over the decompiled `.java` tree. Findings identify risky patterns with evidence for the analyst to review; they are not exploit steps.
- Report exports (JSON and Markdown) include the input SHA-256, source (`device`/`upload`), tool versions, the manifest summary, and the persisted findings, plus a fixed "authorized analysis only" statement.
- Mutating routes (`install`, `decompile`, `import`, `findings` POST, `delete`) require login, CSRF, and audit logging; read routes (`status`, `projects`, `browse`, `file`, `search`, `manifest`, `findings` GET, `report`) require login only.

## Known Limitations

- Java/JDK is a host prerequisite; the app can download jadx itself but does not install OS-level runtimes.
- The source viewer is a plain read-only `<textarea>`, matching the "no build step, no large editor dependency" constraint used across the app.
- Static findings are pattern/regex-based, not a real data-flow or taint analysis -- they are intentionally framed as evidence for a human analyst, not confirmed vulnerabilities.
- `delete_project` removes the decompiled project, its findings, and its report exports, but does not remove the cached pulled/uploaded source file under `workspace/jadx_sources/` -- the same tradeoff `adb/apktool_manager.py`'s `delete_project` makes for its own `SOURCES_DIR`.
- Search and the static-findings source scan are bounded (file-count, per-file size, and wall-clock budgets) rather than exhaustive, to keep a single request from hanging on a very large decompiled tree.

## Testing

- `tests/test_jadx_manager.py`
- `tests/test_jadx_routes.py`

Coverage includes traversal rejection, tool-resolution order (override/PATH/vendor), zip-slip rejection on the managed jadx install, decompile argv shape and the nonzero-exit-with-output/empty-output/cancellation/timeout branches, the local-upload validation and metadata path, project listing/browsing/deletion, literal and regex search, manifest parsing, static-findings categories (manifest- and source-derived), report export round-tripping, and route-level auth/CSRF/traversal/no-write-route checks. Also verified end-to-end against the real `jadx` binary (import -> decompile -> browse -> read -> search -> findings -> manifest -> report -> delete) using a self-built `.jar` test fixture.
