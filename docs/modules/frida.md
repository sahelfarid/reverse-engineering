# Frida

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Manages Android `frida-server`, drives the `frida` Python API for process listing, attach/spawn, message streaming, and a small script store, and exposes a host macOS Frida surface through the local Frida device.

## Files

- `adb/frida_manager.py`
- `routes/frida.py`
- `static/js/frida.js`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/frida/status` | Frida package status and per-device server status. |
| GET | `/api/frida/mac/status` | Host macOS Frida package/local-device status. |
| GET | `/api/frida/mac/tools/status` | Host macOS package/CLI status for `frida` and `frida-tools`. |
| POST | `/api/frida/mac/tools/install` | Install `frida` and `frida-tools` into the API server's Python environment. |
| POST | `/api/frida/mac/tools/update` | Upgrade `frida` and `frida-tools` through pip. |
| POST | `/api/frida/mac/tools/test` | Exercise the local Frida Python API and installed `frida` CLI. |
| GET | `/api/frida/mac/processes` | List local macOS processes with metadata when available. |
| GET | `/api/frida/mac/applications` | List local macOS applications (identifier, name, running/pid). |
| GET | `/api/frida/mac/frontmost` | The foreground macOS application, or null. |
| GET | `/api/frida/mac/system` | Local Frida system parameters for the Mac. |
| GET | `/api/frida/mac/process?q=<name\|pid>` | One macOS process with metadata. |
| POST | `/api/frida/mac/spawn-gating/enable` | Suspend newly spawned local processes. |
| POST | `/api/frida/mac/spawn-gating/disable` | Stop suspending newly spawned local processes. |
| GET | `/api/frida/mac/pending-spawn` | List local spawn-gated processes awaiting resume/kill. |
| GET | `/api/frida/mac/pending-children` | List local child-gated processes awaiting resume/kill. |
| GET | `/api/frida/mac/events` | Recent local Frida device events; supports `after`/`limit`. |
| POST | `/api/frida/mac/events/wire` | Subscribe to local Frida device signals. |
| POST | `/api/frida/mac/resume/<pid>` | Resume a suspended local process. |
| POST | `/api/frida/mac/kill/<pid>` | Kill a local process by PID through Frida. |
| POST | `/api/frida/mac/kill` | Kill a local process by PID or name (`target` / `pid` / `name` in body). |
| POST | `/api/frida/mac/input/<pid>` | Feed stdin bytes to a local spawned process. |
| POST | `/api/frida/mac/attach` | Attach to or spawn a local macOS target with a script. Optional `runtime`, `params`, and spawn options match the Android attach route. |
| POST | `/api/devices/<serial>/frida/server/push` | Push frida-server to the device. |
| POST | `/api/devices/<serial>/frida/server/start` | Start frida-server (pushing first if needed). |
| POST | `/api/devices/<serial>/frida/server/stop` | Stop frida-server. |
| GET | `/api/devices/<serial>/frida/processes` | List processes (Frida API, falls back to ADB). |
| GET | `/api/devices/<serial>/frida/applications` | List installed applications (identifier, name, running/pid). |
| GET | `/api/devices/<serial>/frida/frontmost` | The application currently in the foreground, or null. |
| GET | `/api/devices/<serial>/frida/system` | Device details Frida reports (`query_system_parameters`: os, arch, access). |
| GET | `/api/devices/<serial>/frida/process?q=<name\|pid>` | One process with metadata (path, ppid, user). |
| POST | `/api/devices/<serial>/frida/spawn-gating/enable` | Suspend every newly spawned process. |
| POST | `/api/devices/<serial>/frida/spawn-gating/disable` | Stop suspending new spawns. |
| GET | `/api/devices/<serial>/frida/pending-spawn` | List spawn-gated processes awaiting resume/kill. |
| GET | `/api/devices/<serial>/frida/pending-children` | List child-gated processes awaiting resume/kill. |
| GET | `/api/devices/<serial>/frida/events` | Recent device events (`spawn-*`, `child-*`, `process-crashed`, `output`); supports `after`/`limit`. |
| POST | `/api/devices/<serial>/frida/events/wire` | Subscribe to device signals (idempotent). |
| POST | `/api/frida/sessions/<session_id>/child-gating/enable` | Follow fork()/exec() children on this session. |
| POST | `/api/frida/sessions/<session_id>/child-gating/disable` | Stop following children. |
| POST | `/api/devices/<serial>/frida/resume/<pid>` | Resume a suspended process. |
| POST | `/api/devices/<serial>/frida/kill/<pid>` | Kill a process by PID via the Frida device API. |
| POST | `/api/devices/<serial>/frida/kill` | Kill by PID or name (`target` / `pid` / `name` in body). |
| POST | `/api/devices/<serial>/frida/input/<pid>` | Feed stdin bytes to a process (`data` + optional `encoding` `utf8`/`hex`). |
| POST | `/api/devices/<serial>/frida/attach` | Attach to or spawn a target with a script. Optional `runtime` (`qjs`/`v8`), `params` object (injected as `const PARAMS`), and spawn options `argv`/`env`/`cwd`/`stdio`. |
| GET | `/api/frida/sessions` | List active sessions (refreshes `is_detached()`). |
| GET | `/api/frida/sessions/<session_id>` | One session's state; polls Frida `is_detached()`. |
| GET | `/api/frida/sessions/<session_id>/stream` | SSE stream of a session's messages. |
| GET | `/api/frida/sessions/<session_id>/export` | Download buffered console log (`format=json` or `text`). |
| GET | `/api/frida/sessions/<session_id>/exports` | List the attached script's `rpc.exports` names. |
| POST | `/api/frida/sessions/<session_id>/exports/<name>` | Invoke an export with positional JSON `args`. |
| POST | `/api/frida/sessions/<session_id>/post` | Send a `message` and/or hex `data` into the script's `recv()` / binary side-channel. |
| POST | `/api/frida/sessions/<session_id>/eternalize` | Eternalize the script (keeps running after client disconnect) then drop the session. |
| POST | `/api/frida/sessions/<session_id>/interrupt` | Interrupt the script's current execution (session stays alive). |
| POST | `/api/frida/sessions/<session_id>/terminate` | Force-terminate a runaway script and drop the session. |
| POST | `/api/frida/sessions/<session_id>/detach` | Detach a session. |
| GET | `/api/frida/scripts` | List stored scripts. |
| POST | `/api/frida/scripts` | Save a script. |
| DELETE | `/api/frida/scripts/<name>` | Delete a script. |

## Behavior

- Provides Frida Python package status, matching frida-server URL resolution/cache/download, server push/start/stop, Frida process listing with ADB fallback, attach/spawn, message streaming, detach, and script store CRUD.
- The macOS host routes use `frida.get_local_device()` and the same session registry/message streaming/RPC/export endpoints as Android. They do not run ADB, download `frida-server`, or perform Android client/server version checks.
- The macOS host tools routes are only active when the API process is running on macOS. Install/update uses the running interpreter (`sys.executable -m pip install [--upgrade] frida frida-tools`), records bounded pip output, refreshes package/CLI status, and audit-logs versions rather than command output. The UI exposes these controls in the Frida tab's Mac scope.
- Classic frida-server operations require `manager.has_root_shell()`.
- `get_status()` reports each device's on-device `server_version` (from `frida-server --version`) and a `version_match` flag against the installed Python `frida`. `attach()` calls `check_version_compatibility()` first and raises a clear error on a major.minor divergence (the frida wire protocol is tied to major.minor), rather than letting attach fail with a cryptic engine error.
- Script names are constrained, default templates are read-only, and script size is capped at 256 KiB. The bundled read-only templates are `template-method-tracer`, `template-ssl-pinning-bypass` (OkHttp/Conscrypt/custom TrustManager/WebView, each hook guarded so unused stacks are skipped), and `template-root-detection-bypass` (File.exists / Runtime.exec / SystemProperties / Build.TAGS / PackageManager / RootBeer). Both bypass agents emit `send()` telemetry per neutralized check and are for authorized testing only.
- Attach audit logs include target, script name, and source hash rather than full source.
- Each session registers a `detached` signal handler; when the target quits/crashes/disconnects, the reason (and a crash summary when present) is recorded on the session and pushed into its message stream as a `{"type": "detached"}` event, and `list_sessions()` exposes `detached`/`detach_reason`.
- Session list/get and live RPC/post paths poll `session.is_detached()` so a missed signal still marks the session detached; the UI also polls `GET /api/frida/sessions/<id>` every few seconds and disables controls when detached.
- `rpc.exports` on an attached script can be listed and invoked over HTTP. Export names are validated (`^[A-Za-z_][A-Za-z0-9_]*$`), args must be a JSON array, detached sessions are rejected, and `bytes` results are JSON-encoded as `{"__bytes_hex__": ...}`. Export calls are audit-logged by name (never args).
- Scripts install a structured `set_log_handler` so `console.log` / `warn` / `error` arrive on the message stream as `{"type": "log", "level": ..., "payload": ...}` and the UI colors them by level.
- Attach accepts optional `runtime` (`qjs` or `v8`) and passes it to `session.create_script(..., runtime=...)`. Invalid values are rejected; the chosen runtime is stored on the session and audit-logged.
- Attach accepts optional `params` (JSON object). It is prepended as `const PARAMS = {...};` so templates can read named load-time values without editing source. Params are size-capped; audit logs only `has_params` (never the values).
- Spawn attach accepts optional `argv` (list), `env`/`envp` (object), `cwd`, and `stdio` (`inherit`/`pipe`) and passes them to `device.spawn()`.
- `input_to_process()` wraps `device.input(pid, data)` for feeding stdin of spawned targets (especially with `stdio=pipe`).
- Device signal handlers (`spawn-added/removed`, `child-added/removed`, `process-crashed`, `output`) are wired on spawn-gating enable, child-gating enable, attach, or explicit `/events/wire`. Events are ring-buffered per serial, polled via `/events`, and fan out into live session consoles.
- Each session keeps a bounded message log (script messages, logs, detach, device events). `GET .../export?format=json|text` downloads it; the UI has Export .txt / .json / binaries, a session switcher (`GET /api/frida/sessions`), structured system/process panels, a device event table with crash reports, kill-by-name, and `script.post` binary hex side-channel.
- `eternalize_session()` calls `script.eternalize()` then detaches without `unload()`, so the agent keeps running on the target after the UI disconnects.
- The session registry and message queues are process-local.

## Known Limitations

- `list_processes()` catches all exceptions and falls back to ADB. That's intentionally user-friendly (a Frida-side USB/device-manager hiccup shouldn't break the process list), covered for both paths.
- Attach target names are not shell-executed (this module talks to the `frida` Python API, not device shell strings, for attach targets), so there's no injection surface to validate beyond what's already covered.

## Testing

- `tests/test_frida_manager.py`
- `tests/test_frida_routes.py`
- Coverage: 87% backend, 97% route

See [`docs/module-audits/frida.md`](../module-audits/frida.md) for the audit history (bugs found and fixed, and any items still open).
