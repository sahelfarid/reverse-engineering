# TODO: Portable cross-platform build (desktop-app-style packaging)

## Objective

Package this Flask panel as a portable, double-click-to-run desktop app on
Windows/macOS/Linux — a native window instead of "open a terminal, run
`python app.py`, open a browser tab" — while keeping the existing Flask app
and all of its routes/templates/static completely unchanged. The web app
stays the source of truth; this is a thin desktop shell + build pipeline
around it, not a rewrite.

Builds on existing code — do not duplicate:
- `app.py:create_app()` — reused as-is; the desktop entrypoint imports and runs it, it does not
  reimplement route registration.
- The existing `127.0.0.1`-only binding and login/CSRF/audit model in `auth.py` — unchanged; the native
  window is just another local HTTP client, not a new trust boundary.
- `config.py`'s `BASE_DIR`/`VENDOR_DIR`/`DATA_DIR` path constants — must be made frozen-build-aware (see
  below) rather than adding a second, parallel path-resolution scheme.

## Approach: pywebview + PyInstaller (not Electron)

Use **pywebview** (wraps the OS's native webview: WebView2 on Windows, WKWebView on macOS, WebKitGTK on
Linux) instead of Electron/CEF — it doesn't bundle a second Chromium, keeping the package an order of
magnitude smaller, and there's no separate JS-side app to maintain since the existing server-rendered
templates + vanilla JS already work unmodified inside any standards-compliant webview.

- [ ] Add `pywebview` to a new `requirements-desktop.txt` (kept separate from `requirements.txt` — the
      web-only deployment path shouldn't need a GUI toolkit dependency).
- [ ] New `desktop.py` entrypoint (does **not** replace `app.py`, which stays usable standalone for
      `python app.py` / server-only deployments):
  - [ ] Pick a free local port at startup (`socket.bind(("127.0.0.1", 0))`, read back the assigned port)
        instead of hardcoding 5000 — avoids collisions if a previous instance's port is still held, and
        removes the last hardcoded-port assumption from the codebase.
  - [ ] Start `app.run(host="127.0.0.1", port=<chosen>, threaded=True)` in a background thread
        (`threading.Thread(daemon=True)`), reusing `app.create_app()` unchanged.
  - [ ] Poll `http://127.0.0.1:<port>/api/adb/status` (already exists, needs no auth) in a short retry
        loop until the server responds, then open the `webview.create_window(...)` pointing at that URL
        — don't just sleep a fixed delay, which is flaky on slow first-boot machines.
  - [ ] `webview.start()` on the main thread (required by most native webview backends).
- [ ] **Single-instance guard**: on startup, check/create a lock file under `data/desktop.lock`
      containing the running port + PID; if a live instance is already running, focus/raise its window
      (or at minimum print "already running" and exit) instead of starting a second server that would
      silently pick a different port and confuse the user about which window is "the real one".

## Frozen-build path handling (the classic PyInstaller + Flask gotcha)

- [ ] `config.py`'s `BASE_DIR` currently resolves via `Path(__file__).resolve().parent`, which breaks
      under PyInstaller's onefile mode (`__file__` points into the temp extraction dir, but
      `templates/`/`static/` need to be found there too — this actually works for onefile since
      PyInstaller extracts everything together, but **does not** work the same way for onedir/onefile
      differences in write-location semantics). Add a `is_frozen()` helper
      (`getattr(sys, "frozen", False)`) and branch:
  - Read-only bundled assets (`templates/`, `static/`) → resolve via `sys._MEIPASS` when frozen.
  - Writable data (`vendor/`, `temp/`, `data/`) → must NOT live inside the temp extraction dir (it's
    wiped between runs for onefile builds); resolve these against a proper per-user app-data directory
    instead (`%LOCALAPPDATA%\AdbDeviceManager` on Windows, `~/Library/Application Support/AdbDeviceManager`
    on macOS, `~/.local/share/adb-device-manager` on Linux) so the generated password, settings,
    known-devices list, macros, and downloaded platform-tools/apktool/frida-server survive across runs
    and app updates.
- [ ] Update `app.py`'s Flask constructor to pass explicit `template_folder`/`static_folder` paths
      resolved through the same frozen-aware helper, rather than relying on Flask's default
      relative-to-`__file__` resolution.

## Build pipeline

- [ ] Per-OS PyInstaller spec files (`build/windows.spec`, `build/macos.spec`, `build/linux.spec`) —
      PyInstaller cannot cross-compile, each spec is built on its target OS.
  - [ ] `--onefile` for simplicity, or `--onedir` if startup time matters more than "single file to
        hand someone" — document the tradeoff, default to onefile for the "portable" framing in this
        doc's title.
  - [ ] Explicitly add `templates/` and `static/` as PyInstaller `datas` (Flask's app won't find them
        otherwise — they're not Python imports, so PyInstaller's default import-scanning misses them).
  - [ ] App icon: `.ico` (Windows), `.icns` (macOS), `.png` (Linux) — placeholder assets to create.
- [ ] Decide, as a build-time flag, whether `vendor/platform-tools` ships pre-bundled in the desktop
      package (bigger download, zero first-run network dependency) vs. staying download-on-first-use as
      today (smaller package, matches the existing bundled-install flow exactly) — document both, default
      to download-on-first-use to keep the packaged binary small and avoid re-bundling Google's zip.
- [ ] CI: GitHub Actions matrix (`windows-latest`, `macos-latest`, `ubuntu-latest`) running the
      corresponding PyInstaller spec and uploading build artifacts — no cross-compilation, one job per OS.
- [ ] Codesigning/notarization (macOS Gatekeeper, Windows SmartScreen) — out of scope for v1, note as a
      stretch goal; unsigned builds will show OS security warnings on first launch, which is acceptable
      for a personal/local dev tool but should be called out to whoever runs the build.

## Nice-to-haves (stretch, not required for v1)

- [ ] System tray icon (`pystray`) with a right-click "Open" / "Quit" menu, so the app can minimize to
      tray instead of fully closing — natural fit given the server keeps running in a background thread
      regardless of window state.
- [ ] Auto-updater — out of scope; would need a release-channel + signature-verification design of its
      own and shouldn't be bolted on casually given this app can run a root shell.

## Security notes

- No change to the trust model documented in `README.md`: still `127.0.0.1`-only, still requires the
  generated/changed login password, still CSRF-protected mutations, still audit-logged privileged
  actions. Packaging as a desktop app must not become an excuse to relax any of that (e.g., do **not**
  add a "remember me forever, skip login" mode just because it's "just a local app now" — the shell/root
  capabilities are exactly as sensitive either way).
- The single-instance lock file and the relocated per-user app-data directory are the only new
  filesystem surfaces this introduces; validate the lock file's PID before trusting it (a stale lock
  file from a crashed previous run should not block a fresh start indefinitely — check
  `psutil.pid_exists(pid)` or platform equivalent before treating the lock as "still running").

## Tests to add

- [ ] `is_frozen()`-aware path resolution, parametrized over frozen/non-frozen, asserting the read-only
      asset paths and writable data paths land in the expected locations for each case.
- [ ] Single-instance lock acquire/detect-stale/release logic (mock PID liveness check) — pure logic,
      no need to actually spawn a second process in the test.
- [ ] Free-port picker returns a port that's actually bindable (smoke test: bind, release, rebind).
