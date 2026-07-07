# ADB Device Manager

A local Flask panel for browsing, testing, and managing Android devices over ADB. It includes device discovery, file transfer, shell access, APKTool decompile/rebuild workflows, JADX decompilation and static analysis, package/app inspection, logcat streaming, screen tools, input automation, backups, network tools, permissions, clipboard helpers, process management, Frida instrumentation, and a portable desktop wrapper.

**This is a local developer tool, not a hosted service.** It binds to `127.0.0.1` only and must never be exposed on a public network. It can run privileged shell actions and modify connected devices, so login, CSRF protection, and audit logging stay enabled even in the desktop build.

## Quick Start

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run.ps1 -Action web
```

Linux/macOS:

```sh
sh scripts/run.sh web
```

The scripts default to a managed `.venv`, install dependencies, and start the web panel at `http://127.0.0.1:5000`. On first run, the browser shows a setup screen to set a login password (optional -- you can skip it) with a "remember me" option; the password (if set) is stored hashed in `data/settings.json`. A "Forgot password? Reset" link on the login page clears the password (and every remembered session) after a confirmation prompt, if you need to start over.

To use the active/system Python instead of `.venv`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run.ps1 -Action web -UseSystemPython
```

```sh
sh scripts/run.sh web --system-python
```

Manual setup still works:

```sh
pip install -r requirements.txt
python app.py
```

If ADB is not installed or on `PATH`, the Dashboard offers an **Install ADB** button. It downloads Google's official platform-tools zip into `vendor/platform-tools/` without admin rights or system PATH changes. APKTool and Frida server status sit beside the ADB status card: APKTool can be downloaded into `vendor/apktool/`, while Frida server install pushes the matching binary to the selected rooted device.

## Desktop App And Builds

The desktop app is a thin `pywebview` shell around the same Flask app. It runs `desktop.py`, picks a free loopback port, starts the server in a background thread, and opens a native webview window. The web app remains the source of truth.

Run desktop mode:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run.ps1 -Action desktop -DesktopDeps
```

```sh
sh scripts/run.sh desktop --desktop-deps
```

Compact launchers:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-gui.ps1
```

```sh
sh scripts/build-gui.sh
```

Build portable packages:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run.ps1 -Action build-windows -DesktopDeps
```

```sh
sh scripts/run.sh build --desktop-deps
```

PyInstaller cannot cross-compile, so each OS must build its own spec: `build/windows.spec`, `build/macos.spec`, or `build/linux.spec`. Outputs land in `dist/`. The GitHub Actions workflow `.github/workflows/desktop-build.yml` builds artifacts on Windows, macOS, and Linux. Builds are unsigned in v1, so Windows SmartScreen and macOS Gatekeeper may warn on first launch.

Desktop dependencies live in `requirements-desktop.txt`; web-only usage only needs `requirements.txt`. Writable app data moves to per-user app-data directories in frozen builds, while templates and static files are bundled read-only.

## Features

- Device discovery, fastboot detection, per-device model/build/battery/storage detail.
- File browser with upload/download, folder export, preview, search, rename, move, copy, mkdir, and delete.
- Shell terminal with safe ADB invocation and optional rooted `su` usage.
- APKTool tab for authorized APK pull, decompile, local edit, rebuild, debug-sign, and reinstall workflows.
- JADX tab for authorized APK/DEX/JAR decompilation (device pull or local upload) to readable Java, with search, manifest summary, static findings, and report export.
- Package management: install, uninstall, enable/disable, clear data, force-stop, launch, restart, APK pull, and size inspection.
- App inspector for permissions, components, data directory access, databases, and backup paths.
- Live logcat over SSE with tag, pid, package, level, and regex filters.
- Screen tools: screenshot, recording, rotation, wake/sleep, brightness.
- Input automation: tap, swipe, text, keyevents, macro record/save/play/import/export.
- Properties, network, wireless ADB, port forward/reverse, known wireless devices.
- Backups for common folders, logcat dumps, APKs, app data, and databases, with background jobs where useful.
- Battery/hardware, runtime permissions, clipboard best-effort helpers, and process listing/killing.
- Frida tab for authorized dynamic instrumentation on rooted devices.
- Desktop wrapper and PyInstaller build pipeline for portable local app usage.

See `features.md` and the modules under `adb/`, `routes/`, and `static/js/` for implementation details.

## Frida Instrumentation

Frida support is for authorized testing on your own devices and apps. Classic `frida-server` requires a rooted device; non-root Frida Gadget APK repackaging is not part of v1.

The Frida tab can:

- Report whether the Python `frida` package is installed and which version is active.
- Resolve and cache the matching Android `frida-server` binary under `vendor/frida/<version>/<arch>/`.
- Push/start/stop `/data/local/tmp/frida-server` using a captured PID, not `killall`.
- List attach targets through Frida with an ADB process-list fallback.
- Attach to a running PID or spawn by package name.
- Load JavaScript hooks, stream `console.log` / `send()` output through SSE, and detach sessions.
- Save user scripts in `data/frida_scripts/` and provide read-only starter templates with authorized-testing copy.

Mutating Frida routes require login and CSRF, and attach/script actions audit the target and script hash rather than storing full script source in the audit log.

## APKTool Workflow

APKTool support is for apps you own, your own test devices, or work where you have explicit authorization.

The APKTool tab can:

- Check Java, cached apktool.jar, signing tools, optional zipalign, and the debug keystore.
- Download the pinned apktool.jar release into `vendor/apktool/apktool.jar`.
- Pull an installed package's APK through the existing package helper and decompile it under `workspace/apktool_projects/<package>/`.
- Browse the decompiled tree with strict local path containment.
- Edit smali/XML/text files in a textarea.
- Rebuild with apktool, optionally zipalign, sign with apksigner or jarsigner, and reinstall through the existing package installer.

Java is required and is not silently installed; use a JRE/JDK such as Adoptium. Android SDK build-tools are recommended for `apksigner` and `zipalign`; a JDK `jarsigner` fallback is supported.

## JADX Static Analysis

JADX support is for apps you own, your own test devices, or work where you have explicit authorization. Unlike APKTool, this is a one-directional decompiler with no rebuild/sign/reinstall and no write-back to the device -- read-only start to finish.

The JADX tab can:

- Check Java and jadx availability (resolved from a settings override, then `PATH`, then the app-managed install) and download the pinned jadx release into `vendor/jadx/`.
- Pull an installed package's APK through the existing package helper, or accept a direct local `.apk`/`.dex`/`.jar` upload, and decompile it under `workspace/jadx_projects/<project>/`.
- Browse the decompiled tree read-only and full-text search across it (literal or regex).
- Parse the decompiled `AndroidManifest.xml` into a permissions/components/SDK summary.
- Run an opt-in static-findings pass (risky manifest flags/permissions, hardcoded secrets, weak crypto, risky WebView/TLS patterns) and export a JSON or Markdown analysis report.

Decompile jobs are cancellable and timeout-bounded through the same background-job system used elsewhere in the app.

## API Surface

All routes are `/api/...` and return JSON except file/image/zip downloads and SSE streams. Grouped by area:

- **Auth/core**: first-launch setup, login, logout, change-password, password reset, ADB status/install, settings, audit log.
- **Devices**: list, per-device detail, overview.
- **Shell**: su-available, exec.
- **Files**: browse, search, mkdir, delete, rename, move, copy, upload, download, folder download, preview.
- **Packages**: list, install, uninstall, disable/enable, clear-data, force-stop, launch, restart, pull APK, size.
- **APKTool**: tool status/install, decompile jobs, project list/browser, file read/save, rebuild jobs, reinstall, delete project.
- **JADX**: tool status/install, decompile jobs (device pull or local upload), project list/browser, read-only file read, search, manifest summary, static findings, report export, delete project.
- **App Inspector**: permissions/components/data-dir detail.
- **Logcat**: SSE stream and clear.
- **Screen**: screenshot, record start/stop/status/pull, rotate, wake/sleep, brightness.
- **Automation**: tap/swipe/long-press/text/keyevent, screen-size, macros CRUD/play.
- **Properties**: categorized `getprop`.
- **Network/Wireless**: info, ping, forward/reverse, tcpip, connect/disconnect, known devices.
- **Backup**: common folder, logcat, APK, database, app-data exports.
- **Battery/Permissions/Clipboard**: hardware detail, grant/revoke, clipboard read/write/history.
- **Processes**: list, kill, foreground app.
- **Frida**: status, server push/start/stop, process list, attach, SSE stream, detach, script CRUD.
- **Jobs**: list, get, cancel, download result.

## Security Model

- Every page requires login, unless a password was deliberately skipped on the first-launch setup screen (an explicit, reversible choice for solo local use -- add a password anytime from Settings, or the login page's "Forgot password? Reset" link clears everything and shows the setup screen again).
- Every mutating request requires an `X-CSRF-Token` header. The frontend uses `apiFetch()` in `static/js/app.js` to attach it.
- Privileged actions are appended to `data/audit.log` and visible from Settings.
- ADB is invoked with argv lists. Dynamic values used inside `adb shell` commands are quoted before being passed as a single remote command string.
- Device serials, package names, process IDs, port specs, and script names are validated before use where they cross trust boundaries.
- The desktop window is only a local HTTP client; it does not weaken the server-side login/CSRF/audit model.

## Development

Run tests:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run.ps1 -Action test
```

```sh
sh scripts/run.sh test
```

Manual test command:

```sh
python -m pytest -q
```

A few tests need a real, authorized ADB device/emulator attached and skip cleanly without one
(see `docs/module-audits/README.md` for details).

Frontend tests (`static/js/*.js`, via Vitest + jsdom, no bundler):

```sh
npm install
npm test
```

To add a new tab: add an `adb/<area>.py` module with pure Python logic, add a `routes/<area>.py` blueprint, register it in `routes/__init__.py`, add a `<section id="tab-<area>">` in `templates/dashboard.html`, and add `static/js/<area>.js` following the existing `onTabChange` / `onDeviceChange` pattern.

## Troubleshooting

- **ADB not installed**: use the Dashboard install button, or check network access to `dl.google.com`.
- **APKTool missing**: use the Dashboard or APKTool tab install button; Java must already be installed.
- **JADX missing**: use the Dashboard or JADX tab install button; Java must already be installed. If a system `jadx` on `PATH` reports a broken version (e.g. a stale `JAVA_HOME`), set an explicit path in Settings > `jadx path override`.
- **APK rebuild cannot sign**: install Android SDK build-tools for apksigner, or a JDK that includes jarsigner/keytool.
- **Device unauthorized**: accept the RSA key prompt on the device and refresh.
- **Device offline**: reconnect USB or restart the ADB server externally.
- **Permission denied browsing files**: protected paths require root; navigate elsewhere or use a rooted test device.
- **Uploads rejected**: check Max upload size in Settings.
- **Desktop build fails on Linux**: install WebKitGTK/PyGObject dependencies for pywebview.
- **Frida server will not start**: confirm the device is rooted, online, and the Python `frida` package is installed.
- **Frida version mismatch**: delete the cached server under `vendor/frida/` and let the app download the binary matching the installed Python package.

## Known Limitations

- Clipboard read is best-effort and restricted on Android 10+.
- Clipboard write requires a helper app listening for a broadcast.
- App data/database export requires `run-as` support or root.
- `ls`, `ps`, and `dumpsys` parsing is best-effort across OEM variants.
- Job cancellation only interrupts steps backed by live subprocess handles.
- Root shell actions require rooted devices or emulators.
- Frida Gadget/non-root APK repackaging, codesigning/notarization, tray mode, and auto-update are out of scope for v1.
- JADX static findings are pattern-based (not a real data-flow/taint analysis) and are meant as evidence for a human analyst, not confirmed vulnerabilities.
