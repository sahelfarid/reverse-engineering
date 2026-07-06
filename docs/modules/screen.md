# Screen

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Screenshots, screen recording, rotation, wake/sleep, and brightness control.

## Files

- `adb/screen.py`
- `routes/screen.py`
- `static/js/screen.js`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices/<serial>/screen/screenshot` | Capture a screenshot. |
| POST | `/api/devices/<serial>/screen/record/start` | Start screen recording. |
| POST | `/api/devices/<serial>/screen/record/stop` | Stop screen recording. |
| GET | `/api/devices/<serial>/screen/record/status` | Current recording status. |
| GET | `/api/devices/<serial>/screen/record/pull` | Pull the finished recording. |
| POST | `/api/devices/<serial>/screen/{rotate,auto-rotate,wake,sleep,brightness}` | Simple actions bound via `_simple_action_route()`. |

## Behavior

- Supports screenshot, screenrecord start/stop/status/pull, rotation lock/set, wake, sleep, and brightness.
- Screenshots use binary `exec-out screencap -p`.
- Recording state is process-local and keyed by serial.
- Brightness is clamped to 0..255; rotation accepts only 0, 90, 180, and 270.
- Mutating routes require login, CSRF, and audit logging.
- `record_start()` and `_simple_action_route()` wrap their `int(...)` conversions of user-supplied JSON (`time_limit_sec`, `degrees`, `level`) in `try/except`, returning a clean 400 instead of an unhandled `ValueError`/`TypeError` on non-numeric input.
- `record_pull()` uses the same `response.direct_passthrough = False` fix as the Files/Backup/Jobs/Packages download routes so its temp-dir cleanup actually runs.

## Known Limitations

- Active recording state is lost on server restart and does not verify the remote PID is still alive; an accepted tradeoff for an in-memory-only, single-user registry.
- `stop_recording()` sends `kill -INT` to a stored PID without revalidating it belongs to `screenrecord`. Left as-is rather than adding an unverified `ps -p <pid>` check: Android's `ps -o` column support varies across toybox/busybox versions, and the PID-reuse window in practice (a single local device, seconds between record-stop calls) is narrow. An accepted risk, not an oversight.

## Testing

- `tests/test_screen.py`
- `tests/test_screen_routes.py`
- Coverage: 100% backend, 97% route

See [`docs/module-audits/screen.md`](../module-audits/screen.md) for the audit history (bugs found and fixed, and any items still open).
