# TODO: jadx integration (APK/dex → readable Java, browse + search)

## Objective

Add a Java-decompilation workflow to the panel: pull an APK (or dex/jar) from a
connected device, decompile it to readable **Java** sources + resources with
[jadx](https://github.com/skylot/jadx), then browse, read, and full-text-search
the decompiled tree in-browser. Follows the same module layout as the rest of
the app: pure-Python logic in `adb/`, a Flask blueprint in `routes/`, one
dashboard tab in `templates/dashboard.html` + `static/js/`.

**Key difference from the apktool module:** jadx is a *one-directional*
decompiler (dex → Java). There is **no rebuild / sign / reinstall** — no
keystore, no `apksigner`/`zipalign`/`jarsigner`, no write-back to the device.
This module is **read-only** with respect to the app and the device. Its value
over apktool is human-readable Java (vs. smali) plus fast cross-project search;
the two are complementary and both consume the same pulled APK.

Builds on existing code — do not duplicate:
- `adb/packages.py:pull_apk()` for getting the APK off the device (same call
  apktool uses).
- `adb/manager.py:run()`/`AdbError` for subprocess-safety conventions
  (list-form argv, never `shell=True`).
- `adb/jobs.py` background job registry for decompile — jadx is CPU-heavy and
  can take a while (tens of seconds to minutes) on large or obfuscated APKs.
- `adb/apktool_manager.py`'s path-traversal helpers (`validate_project`,
  `resolve_project_path`, `_is_relative_to`, `browse_project`) are almost
  identical to what jadx needs. **Prefer extracting these into a small shared
  `adb/_project_fs.py` (or `adb/workspace_fs.py`) helper and importing it from
  both managers**, rather than copy-pasting a second traversal guard. If a
  shared module is judged out of scope for v1, mirror the exact same guards —
  do not weaken them.
- The `routes/files.py` `ls`-table + breadcrumb + preview-modal UI pattern, and
  `static/js/files.js` rendering, for the project file browser.
- The `java_status()` / build-tools detection already in
  `adb/apktool_manager.py` — jadx needs the *same* Java runtime check. Reuse it
  (import `apktool_manager.java_status`) instead of writing a second copy.

## Prerequisites / bundled tooling

- [ ] Java runtime: jadx requires a JRE/JDK (11+). Reuse
      `apktool_manager.java_status()` — if Java is missing, surface the same
      "Java Runtime required" message + adoptium.net link. Do **not** attempt a
      silent JRE install (same reasoning as apktool: JRE installers are
      OS-signed packages, not an extract-and-run zip).
- [ ] Bundle jadx the same way `platform-tools` is bundled (it ships as a zip,
      not a single jar like apktool): download `jadx-<version>.zip` from the
      official GitHub releases into `vendor/jadx/` and extract on first use.
      - `config.py`: add next to `APKTOOL_VERSION` —
        ```python
        JADX_VERSION = "1.5.1"  # pin; bump deliberately
        JADX_URL_TEMPLATE = "https://github.com/skylot/jadx/releases/download/v{version}/jadx-{version}.zip"
        ```
      - The zip extracts to `bin/` (`jadx`, `jadx.bat`, `jadx-gui`, `jadx-gui.bat`)
        and `lib/*.jar`. Invoke the **CLI** launcher only; never the `-gui`
        variant (headless server).
      - Launcher path is OS-specific: `vendor/jadx/bin/jadx` on POSIX,
        `vendor/jadx/bin/jadx.bat` on Windows. On POSIX, `chmod +x` the `bin/`
        scripts after extract (zip perms are unreliable) — mirror how
        `adb.manager.install_adb` marks the extracted `adb` binary executable.
      - Alternative if the `bin` script proves flaky in the frozen build:
        invoke the jars directly with
        `java -cp "vendor/jadx/lib/*" jadx.cli.JadxCLI <args>`. Pick one and
        note it in the module doc; the `bin/jadx` script is preferred because it
        tracks the correct main class across jadx versions.
- [ ] No signing/keystore/build-tools needed — explicitly *not* required for
      this module (call this out so nobody wires in the apktool signing path).

## Module: `adb/jadx_manager.py`

- [ ] `get_status() -> dict` — `{ "ok": True, "java": java_status(),
      "jadx": { "installed": bool, "version": str|None,
      "path": str|None, "pinned_version": config.JADX_VERSION } }`. Derive the
      installed jadx version from `jadx --version` (cache it; it shells out).
- [ ] `ensure_jadx() -> Path` — download + extract the pinned zip into
      `vendor/jadx/` if the launcher isn't already present; return the launcher
      path. Mirror `adb.manager.install_adb`'s download-to-temp → extract →
      chmod flow (stream download, `zipfile.extractall`, atomic-ish move). Guard
      against re-extract when already installed.
- [ ] `_launcher_path() -> str` — OS-appropriate `bin/jadx[.bat]`.
- [ ] `decompile(serial, package, job_id=None, *, no_res=False, deobf=False,
      show_bad_code=True) -> Path` —
      1. `packages.validate_package(package)`.
      2. Check `java_status()`; raise `JadxError(message)` if Java missing.
      3. `ensure_jadx()`.
      4. Reuse `packages.pull_apk(serial, package, source_dir)` to fetch the APK
         (store under `workspace/jadx_sources/<package>/`, same split as
         apktool's `SOURCES_DIR`).
      5. Run the CLI into `workspace/jadx_projects/<package>/`:
         `jadx -d <project_dir> [--no-res] [--deobf] [--show-bad-code]
         [-j <cpu_count>] <apk>`.
         - `--show-bad-code` keeps partially-failed methods visible instead of
           dropping them (useful for RE); default on.
         - `-j <threads>` = `os.cpu_count()` for speed.
         - jadx returns non-zero on *partial* failures even when it produced
           usable output. **Treat "output dir is non-empty" as success even on
           a non-zero exit**, but capture stderr into the job/result so the UI
           can show "decompiled with N warnings". Only hard-fail when the output
           tree is empty.
      6. Stream progress via `jobs.update_job(...)` at pull / decompile / done
         boundaries (same pattern as `apktool_manager.decompile`).
      7. Write a `.jadx-panel` marker (`package=…\ndecompiled_at=<epoch>\n`)
         mirroring apktool's `.apktool-panel`, for `list_projects()`.
- [ ] `list_projects() -> list[dict]` — scan `workspace/jadx_projects/` →
      `{project, package, decompiled_at, size}` (reuse the apktool
      marker/`_dir_size` logic via the shared helper).
- [ ] `browse_project(project, relative_path="") -> dict` — traversal-safe
      breadcrumb browse of the decompiled tree (shared with apktool).
- [ ] `read_project_file(project, relative_path) -> str` — traversal-safe read,
      **read-only** (there is deliberately no `write_project_file` here — jadx
      output is not edited/rebuilt). Cap size / restrict to text extensions
      (`.java`, `.smali`, `.xml`, `.txt`, `.json`, `.properties`, `.kt`, `.gradle`,
      etc.), same guard as apktool's reader.
- [ ] `search_project(project, query, *, max_results=200, ignore_case=True)
      -> list[dict]` — the headline feature. Full-text search across the
      decompiled sources: walk the traversal-validated project root, scan text
      files, return `{path, line, snippet}` hits capped at `max_results`.
      - Treat `query` as a literal substring by default; optional `regex=True`
        with a compiled pattern and a length/complexity cap to avoid ReDoS.
      - Skip binary/oversized files; enforce a total-time or total-files budget
        so a giant project can't hang the request thread.
- [ ] `delete_project(project) -> dict` — `shutil.rmtree` the traversal-checked
      project dir (shared with apktool).
- [ ] `class JadxError(manager.AdbError)` — same base as `ApktoolError`.

## Routes: `routes/jadx.py`

Blueprint `bp = Blueprint("jadx", __name__)`; register in `routes/__init__.py`
next to apktool (`from . import jadx` + `app.register_blueprint(jadx.bp)`).

- [ ] `GET  /api/jadx/status`
- [ ] `POST /api/jadx/install` — download/extract the pinned jadx zip.
- [ ] `POST /api/devices/<serial>/jadx/decompile/<package>` — returns a `job_id`
      (background job via `adb/jobs.py`); accept optional JSON flags
      (`no_res`, `deobf`).
- [ ] `GET  /api/jadx/projects`
- [ ] `GET  /api/jadx/projects/<project>/browse?path=...`
- [ ] `GET  /api/jadx/projects/<project>/file?path=...` — **read only**; no POST
      write route (intentional — mention in the route docstring so it isn't
      "helpfully" added later).
- [ ] `GET  /api/jadx/projects/<project>/search?q=...&regex=0` — returns hit
      list.
- [ ] `DELETE /api/jadx/projects/<project>` — delete a local project directory.

All mutating routes (`POST`/`DELETE`): `@auth.login_required` +
`@auth.csrf_protect` + `auth.audit_log(...)`, identical to every other module.
Read routes (`GET` browse/file/search/projects/status): `@auth.login_required`
only, matching how `routes/apktool.py` gates its reads.

## Frontend: "JADX" tab

Add a `data-tab="jadx"` nav entry + `#tab-jadx` pane in `dashboard.html` and a
`static/js/jadx.js`, registered like `apktool.js`. Reuse `apktool.js` /
`files.js` patterns heavily — this is a near-clone minus the edit/rebuild path.

- [ ] Status card (Java + jadx availability + pinned version + "Install jadx"
      button), same visual pattern as the ADB / apktool status cards.
- [ ] Package picker (reuse the Packages tab's package list) + a "Decompile with
      jadx" button → shows job progress via the existing Jobs panel pattern.
      Optional checkboxes: "skip resources" (`--no-res`, faster) and
      "deobfuscate names" (`--deobf`).
- [ ] Project list (package, decompiled timestamp, size) → "Open" loads a
      breadcrumb file browser (reuse `files.js` table/breadcrumb rendering)
      scoped to the project directory.
- [ ] **Read-only** source viewer for `.java`/`.smali`/`.xml`/text: a
      `<pre>`/`<textarea readonly>` is enough for v1 — no CodeMirror/Monaco
      dependency (keep the "no build step" constraint). No Save button (this
      differs from the apktool tab on purpose).
- [ ] **Search box** scoped to the open project → calls the search endpoint,
      renders `path:line` hits; clicking a hit opens that file in the viewer.
      This is the main reason to add jadx alongside apktool — make it prominent.
- [ ] "Delete project" button per project.
- [ ] Authorization banner in the tab copy (see below), consistent with the
      Shell / Frida / apktool tabs.

## Security / scope notes

- Decompiled projects live under `workspace/jadx_projects/` and the tool under
  `vendor/jadx/` — both already covered by `.gitignore` (`workspace/`,
  `vendor/`). Confirm, don't re-add.
- Validate `project` and `path` params strictly (alnum + `.`/`_`/`-`/`/` only,
  reject `..` segments and absolute paths) **before** touching the filesystem —
  this is the same real local-path-traversal surface as apktool's project
  browser. The read + search endpoints both walk user-named paths, so both must
  go through the traversal guard.
- `regex=True` search must compile with a size cap and run under a time/space
  budget to avoid a ReDoS or a full-tree scan hanging the worker thread.
- This tool decompiles APKs you pull off a device — intended for apps you own,
  your own test devices, or where you otherwise have explicit authorization
  (security research, CTF, coursework). State this in the tab's UI copy,
  consistent with the Shell/Frida/apktool framing. jadx is lower-risk than
  apktool (no write-back to the device), but the same authorization framing
  applies to *what you decompile*.

## Tests to add

- [ ] `tests/test_jadx_manager.py`
  - [ ] Path-traversal rejection for `read_project_file` and `search_project`
        (`../../etc/passwd`, absolute paths, symlink escape) — the exact cases
        apktool tests, applied to the read + search entry points.
  - [ ] `get_status()` reporting logic with mocked `shutil.which` / subprocess
        (java missing; jadx missing; both present).
  - [ ] `decompile(...)` with mocked `pull_apk` + subprocess: assert the exact
        argv passed to the jadx launcher (list form, `-d <dir>`, flags), and
        assert the **non-zero-exit-but-non-empty-output ⇒ success (with
        warnings)** behavior, plus **empty-output ⇒ raise `JadxError`**.
  - [ ] `search_project(...)` against a small fixture tree: literal match,
        `ignore_case`, `max_results` cap, and that binary/oversized files are
        skipped.
  - [ ] `ensure_jadx()` extract/chmod path with a mocked download (a tiny fake
        zip), asserting the launcher ends up executable on POSIX.
- [ ] `tests/test_jadx_routes.py`
  - [ ] Auth/CSRF protection on `decompile` / `install` / `DELETE`
        (401 without login, 403 without CSRF).
  - [ ] `GET .../file` and `.../search` reject traversal params with a 4xx.
  - [ ] Confirm there is **no** file-write route (assert `POST .../file` is 404
        / not registered) — locks in the read-only contract.

## Docs (mirror the apktool paperwork)

- [ ] `docs/modules/jadx.md` — permanent module documentation.
- [ ] `docs/module-audits/jadx.md` — audit checklist/history.
- [ ] Add a JADX row to `features.md` and the module table in `README.md`.
- [ ] Once implemented, add a short `## Status: Implemented` note to the top of
      this file (or fold it into `docs/modules/jadx.md`) the way `todo-frida.md`
      did, and check the boxes above.
