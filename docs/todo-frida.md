# TODO: Frida integration (dynamic instrumentation)

## Objective

Add dynamic instrumentation to the panel: push/run `frida-server` on the
device, attach to (or spawn) a target app process, inject JS hook scripts,
and stream hook output (console.log / send()) back to the browser live.
This is the highest-risk capability added to this app so far — arbitrary
JS execution inside a target process — so it gets the same login+CSRF+audit
gating as everything else, plus explicit UI copy about authorized use.

Builds on existing code — do not duplicate:
- `adb/devices.py:get_basic_properties()` for `ro.product.cpu.abi` (picks the right frida-server build).
- `adb/manager.py:has_root_shell()` — classic frida-server requires root; reuse the same check already
  used by `adb/backup.py` and `adb/process_manager.py` rather than re-implementing root detection here.
- `adb/process_manager.py:list_processes()` for the attach-target picker (don't re-query `ps` separately).
- `adb/logcat.py`'s SSE streaming pattern (`Response(stream_with_context(...), mimetype="text/event-stream")`)
  for the live hook-console output — same shape, different source.
- `adb/jobs.py` if server push/start ends up slow enough to warrant a progress bar.

## Prerequisites

- [x] Python-side: add `frida-tools` (or the `frida` core bindings) to `requirements.txt`, guarded —
      import lazily inside `adb_toolkit/frida_manager.py` and report "frida package not installed" via
      `get_status()` rather than making the whole app fail to boot if it's missing (mirrors how ADB
      itself is optional-until-installed).
- [x] Device-side: `frida-server` binary matching (a) the installed `frida` Python package's version
      exactly and (b) the device's ABI (`arm`, `arm64`, `x86`, `x86_64` — map from
      `ro.product.cpu.abi`). Download from `https://github.com/frida/frida/releases/download/<version>/
      frida-server-<version>-android-<arch>.xz`, decompress, push to `/data/local/tmp/frida-server`,
      `chmod 755`.
- [x] **Root requirement**: classic frida-server needs root to bind and inject. Check
      `manager.has_root_shell(serial)` up front and show a clear "device must be rooted" message if not
      — do not attempt the frida-gadget (non-root, repackage-the-APK) workflow in v1; that's a much
      larger feature (APK repackaging + gadget config), track as a stretch goal, not this TODO's scope.

## Module: `adb_toolkit/frida_manager.py`

- [x] `get_status() -> dict` — frida Python package installed + version, matching frida-server cached
      locally, per-connected-device: server pushed / running / stopped.
- [x] `resolve_frida_server_url(frida_version, abi) -> str` — arch-name mapping table (abi → frida arch
      suffix), analogous to `config.get_platform_tag()`.
- [x] `ensure_frida_server(serial) -> Path` — download+cache under `vendor/frida/<version>/<abi>/frida-server`.
- [x] `push_and_start_server(serial) -> dict` — `adb push`, `chmod`, then start via
      `su -c '/data/local/tmp/frida-server &'` (background on-device, same pattern as
      `adb/screen.py:start_recording`'s `echo $!` pid-capture, so it can be stopped cleanly later).
- [x] `stop_server(serial) -> dict` — `su -c kill -9 <pid>` using the captured pid (don't
      `killall frida-server`, which would also kill other tools' sessions).
- [x] `list_processes(serial) -> list[dict]` — via `frida.get_device_manager()` / `device.enumerate_processes()`,
      falling back to `adb.process_manager.list_processes()` if the frida device connection isn't up yet.
- [x] `attach(serial, target, script_source) -> session_id` — `frida.get_usb_device().attach(pid_or_name)`
      (or `.spawn()` + `.resume()` for a fresh launch), `session.create_script(script_source)`,
      `script.on("message", handler)`, `script.load()`. Track live sessions in an in-memory registry
      (same shape as `adb/jobs.py`'s job registry: id → {process, session, script, message_queue}).
- [x] `detach(session_id) -> dict` — `script.unload()`, `session.detach()`.
- [x] Script store: `save_script(name, source)` / `list_scripts()` / `delete_script(name)` persisted to
      `data/frida_scripts/<name>.js` (mirrors `config.load_macros()`/`save_macros()` for automation).
- [x] Ship 2-3 starter script templates as read-only defaults (not user-deletable), clearly labeled for
      *your own apps / authorized test targets*:
  - [x] Generic method tracer (hook a class+method, log args/return value).
  - [x] Root-detection bypass example (hooks common `File.exists()`/`RootBeer`-style checks) — label
        explicitly as a defensive-testing example (verifying your own app's root-detection logic),
        not a jailbreak/anti-cheat bypass tool.
  - [x] SSL pinning bypass example (for testing your own app's network traffic in a proxy) — same
        "your own app" framing.

## Routes: `routes/frida.py`

- [x] `GET /api/frida/status`
- [x] `POST /api/devices/<serial>/frida/server/push`
- [x] `POST /api/devices/<serial>/frida/server/start`
- [x] `POST /api/devices/<serial>/frida/server/stop`
- [x] `GET /api/devices/<serial>/frida/processes`
- [x] `POST /api/devices/<serial>/frida/attach` — `{target, script_name | script_source}` → `{session_id}`
- [x] `GET /api/frida/sessions/<session_id>/stream` — SSE, same shape as `routes/logcat.py:stream`
- [x] `POST /api/frida/sessions/<session_id>/detach`
- [x] `GET/POST/DELETE /api/frida/scripts` — script library CRUD

All mutating routes: `@auth.login_required` + `@auth.csrf_protect` + `auth.audit_log(...)` — attach and
script execution specifically should log the full script name/source hash (not full source, to keep
audit log entries small) plus target process.

## Frontend: "Frida" tab

- [x] Status card: frida package / server-pushed / server-running, mirroring the ADB status card.
- [x] Server controls: Push, Start, Stop buttons (disabled with a tooltip when the device isn't rooted).
- [x] Target picker: reuse the Processes tab's process table style; add a "spawn by package" input as
      an alternative to attaching to a running pid.
- [x] Script editor: `<textarea>` + a template dropdown (starter scripts) + user script save/load,
      matching the Automation tab's macro save/load UX.
- [x] Live console pane: EventSource-driven, same rendering approach as `static/js/logcat.js`
      (color-code by message type: `send()` payload vs `error`).
- [x] Detach/Stop button, and a clear "authorized testing only" banner at the top of the tab (same
      treatment as the Clipboard tab's limitation banner).

## Security / scope notes

- This is the single most powerful capability in the app (arbitrary code execution inside a target
  process). Keep the existing login+CSRF+audit gating; do not add a separate weaker path.
- Frame all UI copy and starter scripts around *authorized testing on your own devices/apps* — no
  scripts targeting third-party apps, anti-cheat bypass, or DRM circumvention should ship as defaults.
- `frida-server` binaries and any pushed scripts are only ever placed under `/data/local/tmp/` on the
  device and `vendor/`/`data/` locally — both already gitignored.

## Tests to add

- [x] `resolve_frida_server_url` ABI→arch mapping table.
- [x] Script store CRUD (save/list/delete), including rejecting path-traversal-y script names.
- [x] Attach/detach session-registry lifecycle with a mocked `frida` module (no real device/frida
      binary needed for unit tests — mock `frida.get_usb_device()` and assert the registry's state
      transitions, same style as `tests/test_jobs.py`).
