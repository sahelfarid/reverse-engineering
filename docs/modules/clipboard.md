# Clipboard

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Reads and writes the device clipboard, and keeps a bounded local history of what has passed through it.

## Files

- `adb/clipboard.py`
- `clipboard routes in routes/battery.py`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices/<serial>/clipboard` | Read current clipboard contents. |
| POST | `/api/devices/<serial>/clipboard` | Set clipboard contents. |
| GET | `/api/devices/<serial>/clipboard/history` | Read this serial's in-memory clipboard history. |

## Behavior

- Clipboard read is best-effort via raw Android clipboard service binder output parsing.
- Clipboard write uses the historical Clipper broadcast convention and clearly reports that a helper app is required.
- Clipboard history is process-local and bounded to 50 entries per serial, with consecutive-duplicate dedup.
- The write route requires login, CSRF, and audit logging.

## Known Limitations

- Android clipboard restrictions make read behavior inherently unreliable on Android 10+ -- an inherent platform limitation, not a code bug.
- In-memory history is not persisted and is not encrypted; clipboard contents can be sensitive, but this is a documented tradeoff for a local single-user tool.

## Testing

- `tests/test_clipboard.py`
- `tests/test_clipboard_routes.py`
- Coverage: 95% backend, 100% route

See [`docs/module-audits/clipboard.md`](../module-audits/clipboard.md) for the audit history (bugs found and fixed, and any items still open).
