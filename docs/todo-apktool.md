# TODO: apktool integration (APK decompile/edit/rebuild/reinstall)

## Objective

Add a reverse-engineering workflow to the panel: pull an APK from a
connected device, decompile it to smali + resources with apktool, browse
and edit the decompiled sources in-browser, rebuild, sign, and reinstall
back onto the device. Follows the same module layout as the rest of the
app: pure-Python logic in `adb/`, a Flask blueprint in `routes/`,
one dashboard tab in `templates/dashboard.html` + `static/js/`.

Builds on existing code — do not duplicate:
- `adb/packages.py:pull_apk()` for getting the APK off the device.
- `adb/packages.py:install_apk()` for pushing the rebuilt APK back.
- `adb/manager.py:run()`/`quote_remote()`/`AdbError` for subprocess safety conventions.
- `adb/jobs.py` background job registry for decompile/rebuild (both can take a while on large APKs).
- The files.py `ls`-table + preview-modal UI pattern for the project file browser.

## Prerequisites / bundled tooling

- [x] Detect Java: `java -version` via `shutil.which("java")` + subprocess; if missing, show a clear
      "Java Runtime required for apktool" message with a link to adoptium.net — do not attempt a
      silent JRE install (unlike the platform-tools zip, JRE installers are OS-signed packages, not a
      simple extract-and-run zip).
- [x] Bundle apktool the same way platform-tools is bundled: download `apktool.jar` from the official
      GitHub releases (`https://github.com/iBotPeaches/apktool/releases`) into `vendor/apktool/apktool.jar`
      on first use; store the pinned version in `config.py` next to `PLATFORM_TOOLS_URL_TEMPLATE`.
- [x] Signing: need a debug keystore. Generate one on first use via the JDK's bundled `keytool`
      (`keytool -genkey -v -keystore vendor/debug.keystore -alias androiddebugkey -keyalg RSA
      -keysize 2048 -validity 10000 -storepass android -keypass android`), store it under `vendor/`
      (gitignored, treat as sensitive).
- [x] Sign rebuilt APKs with `apksigner` if available (from Android SDK build-tools) else fall back to
      `jarsigner` (bundled with the JDK) — apksigner isn't in platform-tools, so detect it via
      `ANDROID_HOME`/`ANDROID_SDK_ROOT`/settings override and degrade gracefully with a clear message
      if neither is found, same pattern as the existing "requires root/run-as" limitation messages.
- [x] Optional: `zipalign` (also from build-tools) before signing, for stricter compliance — skip
      silently if unavailable, note it in the rebuild result.

## Module: `adb/apktool_manager.py`

- [x] `get_status() -> dict` — java present/version, apktool.jar present/version, apksigner/zipalign
      availability, debug keystore present.
- [x] `ensure_apktool() -> Path` — download+cache apktool.jar (mirrors `adb.manager.install_adb`'s
      download/extract pattern).
- [x] `decompile(serial, package, job_id=None) -> Path` — pull the APK (reuse `adb.packages.pull_apk`),
      run `java -jar apktool.jar d <apk> -o <project_dir> -f`, store output under
      `workspace/apktool_projects/<package>/`.
- [x] `list_projects() -> list[dict]` — scan `workspace/apktool_projects/` for existing decompiles
      (package, decompiled_at, size).
- [x] `read_project_file(project, relative_path) -> str` / `write_project_file(...)` — **must** resolve
      `relative_path` against the project root and reject any path that escapes it
      (`Path(project_dir, relative_path).resolve()` must stay under `project_dir.resolve()`); this is a
      real local-path-traversal surface, unlike the device-side file browser where "traversal" is just
      normal device filesystem access.
- [x] `rebuild(project, job_id=None) -> Path` — `java -jar apktool.jar b <project_dir> -o <out.apk>`,
      then sign (+ optional zipalign), return the final signed APK path.
- [x] `reinstall(serial, signed_apk_path) -> dict` — reuse `adb.packages.install_apk`.

## Routes: `routes/apktool.py`

- [x] `GET /api/apktool/status`
- [x] `POST /api/apktool/install` — download/cache the pinned apktool jar.
- [x] `POST /api/devices/<serial>/apktool/decompile/<package>` — returns a `job_id` (background job,
      per `adb/jobs.py`), since decompiling a large system APK can take a while.
- [x] `GET /api/apktool/projects`
- [x] `GET /api/apktool/projects/<project>/browse?path=...` — mirrors `routes/files.py:browse` but for
      the local decompiled tree.
- [x] `GET/POST /api/apktool/projects/<project>/file?path=...` — read/save a single smali/xml/text file.
- [x] `POST /api/apktool/projects/<project>/rebuild` — background job.
- [x] `POST /api/devices/<serial>/apktool/projects/<project>/reinstall`
- [x] `DELETE /api/apktool/projects/<project>` — delete a local project directory.

All mutating routes: `@auth.login_required` + `@auth.csrf_protect` + `auth.audit_log(...)`, same as
every other module.

## Frontend: "APKTool" tab

- [x] Status card (java/apktool/signing tool availability), same visual pattern as the ADB status card.
- [x] Package picker (reuse the Packages tab's package list) + "Decompile" button → shows job progress
      via the existing Jobs panel pattern.
- [x] Project list (package name, decompiled timestamp) → "Open" loads a breadcrumb file browser
      (reuse `files.js`'s table/breadcrumb rendering approach) scoped to the project directory.
- [x] Simple text editor for smali/XML/text files: a `<textarea>` is enough for v1 — no need for a full
      code-editor dependency (CodeMirror/Monaco) unless later requested; keep consistent with "no build
      step" constraint used everywhere else in this app.
- [x] "Rebuild & Reinstall" button → background job → on completion, install button becomes active.

## Security / scope notes

- Decompiled projects and the debug keystore live under `workspace/`/`vendor/` — gitignore both.
- Validate `project` and file path parameters strictly (alnum + `.`/`_`/`/` only, no `..` segments)
  before touching the filesystem.
- This tool decompiles/rebuilds/reinstalls APKs — intended for apps you own, your own test devices, or
  where you otherwise have explicit authorization (security research, CTF, coursework). Note this in
  the tab's UI copy, consistent with how the Shell/Frida tabs should also be framed.

## Tests to add

- [x] Path-traversal rejection for `read_project_file`/`write_project_file` (e.g. `../../etc/passwd`,
      absolute paths, symlink escape).
- [x] `get_status()` reporting logic with mocked `shutil.which`/subprocess results (java missing,
      apktool missing, both present).
- [x] Rebuild pipeline with mocked subprocess calls (decompile → edit → rebuild → sign), asserting the
      exact argv passed to `java -jar ...` (list form, no shell=True).
