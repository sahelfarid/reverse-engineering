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

## Non-goals

- No app-store scraping or unauthorized APK acquisition — input is always
  either pulled from a device the operator controls or a local file the
  operator explicitly selects/uploads.
- No automated exploit generation from findings (see "Static security checks"
  below) — findings identify risky patterns with evidence, not exploit steps.
- No signing/repacking in this module — that is the apktool module's job.
- No cloud upload of binaries, sources, manifests, or reports; everything
  stays under `workspace/`/`vendor/` on disk, matching every other module.
- No execution of decompiled or imported code, ever — this is a static,
  read-only analysis workflow.

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
- [ ] Detect an existing `jadx` on `PATH` first (`shutil.which("jadx")`) before
      falling back to the managed `vendor/jadx/` install — avoids a redundant
      download when the operator already has it, same reasoning as the ADB
      "use system binary if present" behavior.
- [ ] Add a settings override for a custom jadx binary path, mirroring
      `adb_path_override`/`android_sdk_path_override` in `config.py`:
      `"jadx_path_override": None` in `DEFAULT_SETTINGS`, with the same
      `_is_optional_str` validator. Resolution order: override → `PATH` →
      managed `vendor/jadx/` install.
- [ ] Zip-slip protection when extracting the **downloaded jadx tool archive**
      itself (distinct from the project-path traversal guards below, which
      protect *browsing already-decompiled output*): reuse
      `adb.manager._safe_extract(zf, dest)` (already used by `install_adb` for
      the platform-tools zip) instead of a bare `zipfile.ZipFile.extractall`.

## Module: `adb/jadx_manager.py`

- [ ] `get_status() -> dict` — `{ "ok": True, "java": java_status(),
      "jadx": { "installed": bool, "version": str|None,
      "path": str|None, "pinned_version": config.JADX_VERSION } }`. Derive the
      installed jadx version from `jadx --version` (cache it; it shells out).
- [ ] `ensure_jadx() -> Path` — download + extract the pinned zip into
      `vendor/jadx/` if the launcher isn't already present; return the launcher
      path. Mirror `adb.manager.install_adb`'s download-to-temp → extract →
      chmod flow (stream download, extract via `adb.manager._safe_extract`,
      atomic-ish move). Guard against re-extract when already installed.
- [ ] `_launcher_path() -> str` — resolves in order: `jadx_path_override`
      setting → `shutil.which("jadx")` → managed `vendor/jadx/bin/jadx[.bat]`.
- [ ] `decompile(serial, package, job_id=None, *, no_res=False, deobf=False,
      show_bad_code=True) -> Path` — device-sourced path —
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
         - Run via `subprocess.Popen` (not `subprocess.run`), register the
           child with `jobs.set_job_process(job_id, process)` so
           `jobs.cancel_job` can terminate it mid-run, and poll
           `jobs.is_cancelled(job_id)` between output reads — mirrors
           `jobs.run_adb_with_progress`'s cancel/timeout handling. Bound how
           much stdout/stderr is buffered in memory (e.g. keep only the last
           ~200 lines for the error message) so a very chatty/obfuscated APK
           can't exhaust memory.
         - Enforce a hard wall-clock timeout (settings-configurable, default a
           few minutes) and terminate + raise `JadxError("operation timed
           out")` past it, same shape as the existing shell/timeout pattern
           elsewhere in the app.
      6. Compute the input APK's SHA-256 while/after pulling it and store it in
         the project marker (see below) — lets the UI show a hash and lets a
         later report export cite exactly what was analyzed.
      7. Stream progress via `jobs.update_job(...)` at pull / decompile / done
         boundaries (same pattern as `apktool_manager.decompile`).
      8. Write a `.jadx-panel` marker (`package=…\ndecompiled_at=<epoch>\n
         sha256=<hex>\nsource=device\n`) mirroring apktool's
         `.apktool-panel`, for `list_projects()`.
- [ ] `import_local_artifact(file_storage, display_name=None) -> Path` —
      **local-upload path**, for analyzing an APK/DEX/JAR the operator already
      has on disk (not every target is pulled live off a device — a lab sample,
      a CTF binary, a build artifact). Reuses `routes/files.py`'s upload
      pattern: accept only `.apk`/`.dex`/`.jar` extensions, enforce the
      existing `max_upload_mb` setting (`routes/files.py:131`'s
      `max_bytes` check) before writing, stream to
      `workspace/jadx_sources/<generated-id>/`, compute SHA-256, then hand off
      to the same decompile step as the device path (factor the "run jadx on
      this apk path" core out of `decompile()` so both entry points share it).
      Store `source=upload` in the project marker instead of `source=device`.
- [ ] `list_projects() -> list[dict]` — scan `workspace/jadx_projects/` →
      `{project, package, decompiled_at, size, sha256, source}` (reuse the
      apktool marker/`_dir_size` logic via the shared helper; `source` is
      `"device"` or `"upload"` per above).
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

### Manifest metadata extraction

jadx already decompiles the binary `AndroidManifest.xml` into plain, readable
XML as a normal part of its output — no extra AXML-parsing dependency needed,
just read the file jadx already wrote.

- [ ] `manifest_summary(project) -> dict` — locate the decompiled
      `AndroidManifest.xml` under the project root (traversal-safe, via
      `resolve_project_path`), parse it with the stdlib
      `xml.etree.ElementTree`, and extract: package name, `versionCode`/
      `versionName`, min/target/compile SDK, application label,
      `android:debuggable`, `android:allowBackup`, a
      `networkSecurityConfig` reference if present, and lists of
      permissions/`uses-feature`/activities/services/receivers/providers with
      each component's `exported` flag and intent-filter actions.
- [ ] Handle the "manifest not found" case (decompile failed before producing
      resources, or `--no-res` was used) with a clear "resources were skipped
      for this project" message rather than a stack trace.
- [ ] Label anything reconstructed by jadx (as opposed to a literal 1:1 copy)
      as decompiler-inferred where it matters — mainly relevant for obfuscated
      names, not the manifest itself, but keep the framing consistent with the
      findings model below.

### Static security checks (optional pass)

A lightweight, local, regex/text-pattern pass over the manifest summary and
the decompiled Java sources — flags patterns for the analyst to review, it
does not generate exploits or bypass code.

- [ ] `run_static_checks(project) -> list[dict]` → each finding:
      `{id, severity, confidence, title, file, line, snippet, note}`.
- [ ] Manifest-derived checks (from `manifest_summary()`): exported components
      without a permission attribute, `debuggable=true`, `allowBackup=true`,
      cleartext traffic allowed, a custom network security config with trust
      anchors, and a curated risky-permission list (SMS, contacts, location,
      microphone, camera, `REQUEST_INSTALL_PACKAGES`, accessibility service,
      overlay, notification listener, VPN).
- [ ] Source-derived checks (line-scan the decompiled `.java` tree, reusing
      `search_project`'s traversal-safe file walk): hardcoded URLs/IPs/API
      keys/tokens, weak crypto (`DES`, `ECB`, MD5/SHA-1 for signatures, static
      IVs, `java.util.Random` used where `SecureRandom` belongs), risky WebView
      settings (`setJavaScriptEnabled`, `setAllowFileAccess`,
      `addJavascriptInterface`), TLS-bypass patterns (permissive
      `TrustManager`, a `HostnameVerifier` that always returns true),
      dynamic-code-loading hot spots (`DexClassLoader`, `PathClassLoader`), and
      insecure-storage hints (secrets written to `SharedPreferences`,
      world-readable/writable file modes).
- [ ] Root/emulator/anti-debug detection code is flagged for analyst
      *awareness* only — never turn a finding into bypass guidance.
- [ ] Persist findings to `<project_dir>/../jadx_findings/<project>.json` (or
      a `.jadx-findings.json` marker alongside `.jadx-panel`) rather than a
      database — this app has no SQL store; every other module persists
      JSON under `data/`/`workspace/`, stay consistent with that.
- [ ] This pass is opt-in per project (a button, not automatic on every
      decompile) since it adds scan time on top of decompilation.

## Routes: `routes/jadx.py`

Blueprint `bp = Blueprint("jadx", __name__)`; register in `routes/__init__.py`
next to apktool (`from . import jadx` + `app.register_blueprint(jadx.bp)`).

- [ ] `GET  /api/jadx/status`
- [ ] `POST /api/jadx/install` — download/extract the pinned jadx zip.
- [ ] `POST /api/devices/<serial>/jadx/decompile/<package>` — returns a `job_id`
      (background job via `adb/jobs.py`); accept optional JSON flags
      (`no_res`, `deobf`).
- [ ] `POST /api/jadx/import` — **local-upload path**: multipart file upload
      (`.apk`/`.dex`/`.jar` only), enforcing `max_upload_mb` the same way
      `routes/files.py`'s upload route does; kicks off `import_local_artifact`
      + decompile as a background job, returns a `job_id`.
- No jadx-specific cancel route needed — the generic
  `POST /api/jobs/<job_id>/cancel` in `routes/jobs.py` already calls
  `adb_jobs.cancel_job(job_id)`, which works for any job type as long as
  `decompile()` registers its subprocess via `jobs.set_job_process` (see
  above).
- [ ] `GET  /api/jadx/projects`
- [ ] `GET  /api/jadx/projects/<project>/browse?path=...`
- [ ] `GET  /api/jadx/projects/<project>/file?path=...` — **read only**; no POST
      write route (intentional — mention in the route docstring so it isn't
      "helpfully" added later).
- [ ] `GET  /api/jadx/projects/<project>/search?q=...&regex=0` — returns hit
      list.
- [ ] `GET  /api/jadx/projects/<project>/manifest` — manifest summary.
- [ ] `POST /api/jadx/projects/<project>/findings` — run the static-checks pass
      (mutating: writes `findings.json`); `GET` variant returns the last
      persisted result, or `404` if the pass hasn't been run yet.
- [ ] `GET  /api/jadx/projects/<project>/report?format=json|md` — generate and
      stream the export described in "Reporting" below.
- [ ] `DELETE /api/jadx/projects/<project>` — delete a local project directory.

All mutating routes (`POST`/`DELETE`): `@auth.login_required` +
`@auth.csrf_protect` + `auth.audit_log(...)`, identical to every other module.
Read routes (`GET` browse/file/search/projects/status): `@auth.login_required`
only, matching how `routes/apktool.py` gates its reads.

## Reporting

- [ ] `export_report(project, fmt="json") -> Path` in `adb/jadx_manager.py` —
      builds a single export document from data already on disk for that
      project: `sha256`/`source`/`decompiled_at` from the `.jadx-panel`
      marker, the `manifest_summary()` output, the persisted `findings.json`
      if a static-checks pass has been run, and tool versions (jadx + Java,
      from `get_status()`) plus the app's own version string.
- [ ] `fmt="json"` — the full structured document, machine-readable.
- [ ] `fmt="md"` — an analyst-readable Markdown rendering of the same data
      (headings for manifest summary, permissions table, findings by
      severity).
- [ ] Every export's header includes a fixed "Authorized analysis only — this
      report covers a device/app the operator owns or is explicitly
      authorized to test" line, matching the framing already used in the
      Frida/apktool tab copy.
- [ ] Do **not** include local absolute filesystem paths in the export by
      default (use paths relative to the project root) — avoids leaking the
      operator's machine layout into a report they might share.
- [ ] Reuse `send_file`-based streaming like `routes/jobs.py`'s
      `download_job_result`, rather than inlining large JSON/Markdown in a
      normal JSON response body.

## Frontend: "JADX" tab

Add a `data-tab="jadx"` nav entry + `#tab-jadx` pane in `dashboard.html` and a
`static/js/jadx.js`, registered like `apktool.js`. Reuse `apktool.js` /
`files.js` patterns heavily — this is a near-clone minus the edit/rebuild path.

- [ ] Status card (Java + jadx availability + pinned version + "Install jadx"
      button), same visual pattern as the ADB / apktool status cards.
- [ ] Package picker (reuse the Packages tab's package list) + a "Decompile with
      jadx" button → shows job progress via the existing Jobs panel pattern.
      Optional checkboxes: "skip resources" (`--no-res`, faster) and
      "deobfuscate names" (`--deobf`). Include a Cancel button wired to the
      existing generic job-cancel endpoint.
- [ ] "Import local file" control alongside the package picker (a plain file
      input, not a whole second tab) for the `.apk`/`.dex`/`.jar` upload path
      — the operator isn't always analyzing something currently on a
      connected device.
- [ ] Project list (package, decompiled timestamp, size, source
      device/upload, sha256 prefix) → "Open" loads a breadcrumb file browser
      (reuse `files.js` table/breadcrumb rendering) scoped to the project
      directory.
- [ ] **Read-only** source viewer for `.java`/`.smali`/`.xml`/text: a
      `<pre>`/`<textarea readonly>` is enough for v1 — no CodeMirror/Monaco
      dependency (keep the "no build step" constraint). No Save button (this
      differs from the apktool tab on purpose).
- [ ] **Search box** scoped to the open project → calls the search endpoint,
      renders `path:line` hits; clicking a hit opens that file in the viewer.
      This is the main reason to add jadx alongside apktool — make it prominent.
- [ ] **Manifest** sub-view: permissions table, exported-components table,
      SDK/build flags, from `GET .../manifest`.
- [ ] **Findings** sub-view: a "Run static checks" button (calls the opt-in
      findings pass) + a severity-grouped list once results exist, each with
      file/line/snippet/note.
- [ ] **Export report** button (JSON and Markdown) using `GET .../report`,
      wired through the same download pattern as `routes/jobs.py`'s
      `download_job_result` (`response.direct_passthrough` handling already
      established there).
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
- This tool decompiles APKs you pull off a device *or upload directly* —
  intended for apps you own, your own test devices, or where you otherwise
  have explicit authorization (security research, CTF, coursework). State this
  in the tab's UI copy and in every report export header, consistent with the
  Shell/Frida/apktool framing. jadx is lower-risk than apktool (no write-back
  to the device), but the same authorization framing applies to *what you
  decompile*.
- The upload path (`import_local_artifact`) is a new untrusted-input surface
  this module adds beyond apktool's: validate the extension allowlist and
  `max_upload_mb` cap server-side (not just in the frontend `<input accept>`
  hint), and never trust the client-supplied filename for anything beyond
  display — write to a server-generated path.
- Findings and manifest data render decompiled/attacker-influenced strings
  (class names, string resources, URLs) — escape them the same way
  `escapeHtml()` is already used elsewhere in the dashboard before inserting
  into the DOM; don't auto-linkify URLs pulled from decompiled content.
- Treat any file the app decompiles or imports as untrusted input: this is a
  static-analysis tool, so nothing it processes is ever executed, but that
  also means a hostile jadx *tool* release would be worse than a hostile APK —
  keep the jadx download pinned to a specific version + the official GitHub
  releases URL, same as apktool's `APKTOOL_URL_TEMPLATE`.

## Tests to add

- [ ] `tests/test_jadx_manager.py`
  - [ ] Path-traversal rejection for `read_project_file` and `search_project`
        (`../../etc/passwd`, absolute paths, symlink escape) — the exact cases
        apktool tests, applied to the read + search entry points.
  - [ ] `get_status()` reporting logic with mocked `shutil.which` / subprocess
        (java missing; jadx missing; both present).
  - [ ] `_launcher_path()` resolution order: override setting wins over
        `PATH`, `PATH` wins over the managed `vendor/jadx/` install, mocked
        per case.
  - [ ] `decompile(...)` with mocked `pull_apk` + subprocess: assert the exact
        argv passed to the jadx launcher (list form, `-d <dir>`, flags), and
        assert the **non-zero-exit-but-non-empty-output ⇒ success (with
        warnings)** behavior, plus **empty-output ⇒ raise `JadxError`**.
  - [ ] `decompile(...)` cancellation: a mocked long-running process is
        terminated when `jobs.cancel_job` fires mid-run, and the job ends in
        `cancelled` status, not `error`.
  - [ ] `decompile(...)` timeout: a mocked process that never exits is
        terminated once the wall-clock budget elapses and raises
        `JadxError("operation timed out")`.
  - [ ] `import_local_artifact(...)`: rejects disallowed extensions, rejects
        files over `max_upload_mb`, and produces the same project-marker shape
        (with `source=upload`) as the device path.
  - [ ] `search_project(...)` against a small fixture tree: literal match,
        `ignore_case`, `max_results` cap, and that binary/oversized files are
        skipped.
  - [ ] `ensure_jadx()` extract/chmod path with a mocked download (a tiny fake
        zip), asserting the launcher ends up executable on POSIX, and that a
        zip-slip member (`../../evil`) is rejected before extraction.
  - [ ] `manifest_summary(...)` against a small fixture `AndroidManifest.xml`:
        asserts permissions/exported-components/debuggable/allowBackup are
        parsed correctly, and that a missing manifest produces a clear error
        rather than a stack trace.
  - [ ] `run_static_checks(...)` against fixture snippets: asserts each check
        category (exported-component-without-permission, debuggable,
        hardcoded secret, weak crypto, risky WebView setting, TLS bypass
        pattern) maps to the expected severity, and that findings persist to
        disk and are reloadable.
  - [ ] `export_report(...)`: JSON export round-trips into valid JSON
        containing `sha256`, tool versions, and the authorized-use statement;
        Markdown export contains the same facts in text form.
- [ ] `tests/test_jadx_routes.py`
  - [ ] Auth/CSRF protection on `decompile` / `install` / `import` / `DELETE`
        (401 without login, 403 without CSRF).
  - [ ] `GET .../file` and `.../search` reject traversal params with a 4xx.
  - [ ] Confirm there is **no** file-write route (assert `POST .../file` is 404
        / not registered) — locks in the read-only contract.
  - [ ] `POST /api/jadx/import` rejects an oversized or wrong-extension upload
        with a 4xx before touching the filesystem.
  - [ ] `GET .../manifest`, `.../findings`, and `.../report` all require login
        and reject a traversal-style `project` value.

## Docs (mirror the apktool paperwork)

- [ ] `docs/modules/jadx.md` — permanent module documentation.
- [ ] `docs/module-audits/jadx.md` — audit checklist/history.
- [ ] Add a JADX row to `features.md` and the module table in `README.md`.
- [ ] Once implemented, add a short `## Status: Implemented` note to the top of
      this file (or fold it into `docs/modules/jadx.md`) the way `todo-frida.md`
      did, and check the boxes above.
