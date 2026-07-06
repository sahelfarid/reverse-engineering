# Logcat

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Streams live `adb logcat` output to the browser over Server-Sent Events, with server-side filtering.

## Files

- `adb/logcat.py`
- `routes/logcat.py`
- `static/js/logcat.js`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices/<serial>/logcat/stream` | SSE stream of logcat entries, with tag/pid/level/query filters. |
| POST | `/api/devices/<serial>/logcat/clear` | Clear the device's logcat buffer. |

## Behavior

- Streams `adb logcat -v threadtime` via SSE with optional server-side tag, pid, level, and regex filters.
- Package-to-pid resolution uses `pidof`.
- The clear route requires login, CSRF, and audit logging.
- The subprocess is terminated in a `finally` block when the stream closes, whether from exhaustion or early consumer disconnect.
- An invalid caller-supplied filter regex raises `re.error` internally, which `stream_logcat()` catches and re-raises as `manager.AdbError`, so the route's existing error handling turns it into a clean `event: error` SSE response instead of an unhandled exception mid-stream.

## Known Limitations

- The `TimeoutExpired` -> `process.kill()` fallback in the `finally` block needs a real hung subprocess to exercise meaningfully rather than a mock.

## Testing

- `tests/test_logcat.py`
- `tests/test_logcat_routes.py`
- Coverage: 94% backend, 100% route

See [`docs/module-audits/logcat.md`](../module-audits/logcat.md) for the audit history (bugs found and fixed, and any items still open).
