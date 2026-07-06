# Files

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Full remote file-browser surface: browse, search, CRUD, upload, preview, and single-file/folder download (sync and async).

## Files

- `adb/files.py`
- `routes/files.py`
- `static/js/files.js`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices/<serial>/files/browse` | List a directory. |
| GET | `/api/devices/<serial>/files/search` | Search under a path. |
| POST | `/api/devices/<serial>/files/mkdir` | Create a directory. |
| POST | `/api/devices/<serial>/files/delete` | Delete a file or directory. |
| POST | `/api/devices/<serial>/files/rename` | Rename a path. |
| POST | `/api/devices/<serial>/files/move` | Move a path. |
| POST | `/api/devices/<serial>/files/copy` | Copy a path. |
| POST | `/api/devices/<serial>/files/upload` | Upload a local file to the device. |
| GET | `/api/devices/<serial>/files/preview` | Preview a file (text/image/binary classification). |
| GET | `/api/devices/<serial>/files/download` | Download a single file. |
| GET | `/api/devices/<serial>/files/download-folder` | Download a folder as a zip (sync). |
| GET | `/api/devices/<serial>/files/download-folder/async` | Same, as a background job. |

## Behavior

- Shell path arguments are quoted with `manager.quote_remote()` in the backend for browse/search/CRUD/preview commands.
- Host-side uploads use `secure_filename()` and temporary directories under `config.TEMP_DIR`.
- Download routes (`preview`, `download`, `download-folder`) set `response.direct_passthrough = False` before registering `call_on_close()`. This matters because `send_file()` defaults to `direct_passthrough=True`, and Werkzeug's `Response.get_app_iter()` skips the `ClosingIterator` wrapper in that mode -- the *only* thing that ever calls `Response.close()` (and therefore any registered `call_on_close` callback). Without the explicit `False`, temp directories leak on every request, on any real WSGI server, not just for interrupted clients. **Any future route that does `send_file(...)` followed by `response.call_on_close(...)` must set `direct_passthrough = False` first, or the cleanup callback silently never runs.**
- The async folder-download job's inner `_run()` closure -- which calls `run_adb_with_progress()` and zips the result -- is exercised directly in tests for both the success and cleanup-on-failure paths, in addition to the outer route wiring.

## Known Limitations

- Search queries are quoted, but real `find` behavior on minimal/OEM Android environments (partial permission-denied output) remains a best-effort assumption.
- The upload route checks request content length before saving, but file type and APK/device storage limits are outside its scope -- a documented boundary, not a bug.

## Testing

- `tests/test_files.py`
- `tests/test_files_routes.py`
- Coverage: 98% backend, 95% route

See [`docs/module-audits/files.md`](../module-audits/files.md) for the audit history (bugs found and fixed, and any items still open).
