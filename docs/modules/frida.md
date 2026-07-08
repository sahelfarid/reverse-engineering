# Frida

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Manages `frida-server` on the device and drives the `frida` Python API for process listing, attach/spawn, message streaming, and a small script store.

## Files

- `adb/frida_manager.py`
- `routes/frida.py`
- `static/js/frida.js`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/frida/status` | Frida package status and per-device server status. |
| POST | `/api/devices/<serial>/frida/server/push` | Push frida-server to the device. |
| POST | `/api/devices/<serial>/frida/server/start` | Start frida-server (pushing first if needed). |
| POST | `/api/devices/<serial>/frida/server/stop` | Stop frida-server. |
| GET | `/api/devices/<serial>/frida/processes` | List processes (Frida API, falls back to ADB). |
| GET | `/api/devices/<serial>/frida/applications` | List installed applications (identifier, name, running/pid). |
| GET | `/api/devices/<serial>/frida/frontmost` | The application currently in the foreground, or null. |
| POST | `/api/devices/<serial>/frida/attach` | Attach to or spawn a target with a script. |
| GET | `/api/frida/sessions` | List active sessions. |
| GET | `/api/frida/sessions/<session_id>/stream` | SSE stream of a session's messages. |
| POST | `/api/frida/sessions/<session_id>/detach` | Detach a session. |
| GET | `/api/frida/scripts` | List stored scripts. |
| POST | `/api/frida/scripts` | Save a script. |
| DELETE | `/api/frida/scripts/<name>` | Delete a script. |

## Behavior

- Provides Frida Python package status, matching frida-server URL resolution/cache/download, server push/start/stop, Frida process listing with ADB fallback, attach/spawn, message streaming, detach, and script store CRUD.
- Classic frida-server operations require `manager.has_root_shell()`.
- `get_status()` reports each device's on-device `server_version` (from `frida-server --version`) and a `version_match` flag against the installed Python `frida`. `attach()` calls `check_version_compatibility()` first and raises a clear error on a major.minor divergence (the frida wire protocol is tied to major.minor), rather than letting attach fail with a cryptic engine error.
- Script names are constrained, default templates are read-only, and script size is capped at 256 KiB.
- Attach audit logs include target, script name, and source hash rather than full source.
- The session registry and message queues are process-local.

## Known Limitations

- `list_processes()` catches all exceptions and falls back to ADB. That's intentionally user-friendly (a Frida-side USB/device-manager hiccup shouldn't break the process list), covered for both paths.
- Attach target names are not shell-executed (this module talks to the `frida` Python API, not device shell strings, for attach targets), so there's no injection surface to validate beyond what's already covered.

## Testing

- `tests/test_frida_manager.py`
- `tests/test_frida_routes.py`
- Coverage: 87% backend, 97% route

See [`docs/module-audits/frida.md`](../module-audits/frida.md) for the audit history (bugs found and fixed, and any items still open).
