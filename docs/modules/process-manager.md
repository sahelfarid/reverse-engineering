# Process Manager

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Lists running processes on the device and can kill them.

## Files

- `adb/process_manager.py`
- `routes/process_manager.py`
- `static/js/processes.js`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices/<serial>/processes` | List processes. |
| GET | `/api/devices/<serial>/foreground-app` | Current foreground app (reuses the dashboard implementation). |
| POST | `/api/devices/<serial>/processes/<int:pid>/kill` | Kill a process by PID. |

## Behavior

- Lists processes using `ps -A -o PID,PPID,USER,RSS,NAME`, falls back to `ps -A`, and parses column indexes from the header.
- Reuses the dashboard module's foreground-app implementation.
- Kill sanitizes signal names (strips shell metacharacters, defaults to `TERM` when nothing alphanumeric remains), tries a normal kill first, then a root kill if available.
- The kill route requires login, CSRF, and audit logging.
- Flask's own `<int:pid>` URL converter rejects non-numeric PIDs with a 404 before the view function -- and therefore `kill_process()`'s `int(pid)` -- ever runs; that coercion is retained as a harmless no-op that keeps the function safe to call directly with a numeric string.

## Known Limitations

- The process parser skips rows with fewer columns than the header, which is safe but can hide OEM format drift; inherent to defensive parsing of `ps` output.

## Testing

- `tests/test_process_manager.py`
- `tests/test_process_manager_routes.py`
- Coverage: 93% backend, 100% route

See [`docs/module-audits/process-manager.md`](../module-audits/process-manager.md) for the audit history (bugs found and fixed, and any items still open).
