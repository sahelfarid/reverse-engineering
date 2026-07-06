# ADB Device Manager

A local Flask web panel for browsing and managing Android devices over ADB:
device detection/auto-install, file browsing/transfer, a shell terminal, APK
management, an app inspector, live logcat, screen tools, input automation,
device properties, network/wireless tools, backups, hardware/battery info,
runtime permissions, clipboard, process management, background jobs, and
settings — see `features.md` for the original feature spec this implements.

**This is a local developer tool, not a hosted service.** It binds to
`127.0.0.1` only and must never be exposed on a public network — it can run
an interactive root shell and read/write arbitrary files on any device you
connect.

## Setup

```
pip install -r requirements.txt
python app.py
```

On first run, a random login password is generated and printed once to the
console (hashed and stored in `data/settings.json`). Change it later from the
Settings tab. Open `http://127.0.0.1:5000`.

If ADB isn't installed/on PATH, the Dashboard's status card offers an
**Install ADB** button — it downloads Google's official `platform-tools` zip
for your OS into `vendor/platform-tools/` and uses that directly. No admin
rights, no system PATH changes.

## Architecture

```
app.py               Flask app factory, binds 127.0.0.1 only
config.py             paths + data/settings.json persistence
auth.py                session login, CSRF (X-CSRF-Token header), audit log
adb/                   pure-Python ADB logic, no Flask imports
  manager.py             find/install adb, safe subprocess exec (run/shell/run_binary)
  devices.py              `adb devices -l` parsing, fastboot, per-device props/battery/storage
  dashboard.py             composite overview queries (cpu/mem, screen, foreground app, wifi)
  shell.py                 shell terminal command execution (+ su)
  files.py                 ls -la parsing, browse/CRUD/pull/push/zip
  packages.py               dumpsys package parsing, install/uninstall/enable/disable/launch
  app_inspector.py          permissions/components/data-dir inspection for one app
  logcat.py                  threadtime parsing + live streaming generator
  screen.py                  screenshot/recording/rotation/wake/brightness
  automation.py               tap/swipe/text/keyevent + macro record/playback
  properties.py                getprop categorization
  network.py / wireless.py     network info, port forwarding, tcpip/connect, known devices
  backup.py                     common folder/logcat/apk/app-data/database exports
  battery.py / permissions.py / clipboard.py
  process_manager.py            ps parsing + kill
  jobs.py                        in-memory background job registry (progress/cancel)
routes/                Flask blueprints, one module per adb/ area, all under /api/...
templates/, static/    server-rendered shell + vanilla JS per tab (no build step)
tests/                 pytest suite for the parsing/safety-critical logic
```

### Security model

- Every page requires login (session cookie); every mutating request
  (`POST`/`PUT`/`PATCH`/`DELETE`) requires a matching `X-CSRF-Token` header,
  issued at login and injected by `static/js/app.js`'s `apiFetch()` helper.
- Every privileged action (shell exec, installs, deletes, permission
  changes, wireless connects, etc.) is appended to `data/audit.log` and
  viewable from the Settings tab.
- **No shell string concatenation.** `adb` is always invoked with argv lists
  (`subprocess.run([adb_path, ...])`); dynamic values passed into `adb shell`
  are quoted with `shlex.quote()` and built into a single command string
  before being passed as one argv element (adb re-joins multiple args into
  one string before handing it to the device's shell, so passing them
  separately would not be safe against spaces/metacharacters). File
  transfer always goes through `adb pull`/`push` (the sync protocol), never
  `shell cat`, so the remote shell is only ever used for metadata.
- Package names, device serials, and port specs are validated against strict
  regexes before use.

## API surface

All routes are `/api/...` and return JSON except file/image/zip downloads.
Grouped by area (see the corresponding `routes/*.py` for exact signatures):

- **Auth/core**: login, logout, change-password, adb status/install, settings, audit log
- **Devices**: list, per-device detail, per-device overview
- **Shell**: su-available, exec
- **Files**: browse, search, mkdir, delete, rename, move, copy, upload, download, download-folder (+ `/async` job variant), preview
- **Packages**: list, install (+ `/async`), uninstall, disable/enable, clear-data, force-stop, launch, restart, pull APK, size
- **App Inspector**: permissions/components/data-dir detail
- **Logcat**: SSE stream (tag/pid/package/min_level/query filters), clear
- **Screen**: screenshot, record start/stop/status/pull, rotate/auto-rotate, wake/sleep, brightness
- **Automation**: tap/swipe/long-press/text/keyevent, screen-size, macros CRUD + play
- **Properties**: categorized getprop
- **Network/Wireless**: info, ping, forward/reverse rules, tcpip, connect/disconnect, known devices
- **Backup**: common folder export, logcat dump, APK export, database export, app-data export (+ `/async`)
- **Battery/Permissions/Clipboard**: hardware detail, grant/revoke, clipboard read/write/history
- **Processes**: list, kill, foreground app
- **Jobs**: list, get, cancel, download result

## Known limitations

These are inherent to Android/ADB, not gaps to "fix":

- **Clipboard read** is a best-effort raw `service call clipboard 2` binder
  call; Android 10+ restricts clipboard reads to the focused app, so this
  fails on many devices/OS versions by design, not by bug.
- **Clipboard write** has no built-in ADB command at all — it requires a
  third-party helper app (e.g. "Clipper") listening for a broadcast.
- **App data / database export** requires the target app to be debuggable
  (`run-as`) or the device to be rooted (`su`); otherwise it fails with a
  clear error rather than silently no-op'ing.
- **`ls -la` / `ps` / `dumpsys` parsing** is best-effort across the wide
  range of toybox/busybox/OEM variants; unparseable lines are still shown
  (as `type: "unknown"`) rather than dropped, with a "best effort" banner.
- **Job cancellation** only preempts steps backed by a live subprocess
  handle (adb pull/install). A step run via a blocking shell call (e.g. the
  `tar` step in app-data export) can't be interrupted mid-call — cancel
  takes effect once that call returns.
- **Root shell (`su`) actions** only work on rooted devices/emulators;
  everywhere else they degrade gracefully with an explicit error.

## Troubleshooting

- **"ADB not installed" won't clear after clicking Install** — check your
  network access to `dl.google.com`; the button downloads platform-tools
  directly from Google.
- **Device shows "unauthorized"** — accept the RSA key prompt on the
  device's screen, then hit Refresh.
- **Device shows "offline"** — unplug/replug, or `adb kill-server` and
  reconnect (there's no in-app kill-server button by design, since it would
  drop every device, not just one).
- **Permission denied browsing a folder** — expected for protected system
  paths on a non-rooted device; navigate elsewhere.
- **Uploads rejected** — check the Max upload size setting in the Settings tab.

## Development

```
pip install -r requirements.txt
pytest tests/
```

To add a new tab: add an `adb/<area>.py` module (pure Python, built on
`adb/manager.py`'s `run`/`shell`/`run_binary`), a `routes/<area>.py`
blueprint registered in `routes/__init__.py`, a `<section id="tab-<area>">`
in `templates/dashboard.html`, and a `static/js/<area>.js` following the
existing `onTabChange`/`onDeviceChange` pattern used by every other tab.
