# Backup

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Exports common media folders, logcat dumps, APKs, app databases, and full app-data archives off the device for local inspection.

## Files

- `adb/backup.py`
- `routes/backup.py`
- `static/js/backup.js`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/backup/targets` | List predefined exportable folder targets. |
| GET | `/api/devices/<serial>/backup/export/<key>` | Export a predefined folder target as a zip. |
| GET | `/api/devices/<serial>/backup/logcat` | Dump current logcat to a file. |
| GET | `/api/devices/<serial>/backup/apk/<package>` | Pull a package's APK. |
| GET | `/api/devices/<serial>/backup/database` | Pull an app's sqlite database. |
| GET | `/api/devices/<serial>/backup/app-data` | Export an app's full data directory (sync). |
| GET | `/api/devices/<serial>/backup/app-data/async` | Same, as a background job with progress. |

## Behavior

- Database and app-data exports validate package names through `adb.packages.validate_package()`.
- Database names reject `/`, `.`, and `..`.
- App-data export tries `run-as` first and root fallback (`su 0 tar`) second, then pulls a temporary archive and removes the remote temp file. The root-tar fallback's exit code is checked; a failing tar raises immediately instead of falling through to a confusing pull failure.
- Download routes clean local temp directories via `call_on_close()`, with `response.direct_passthrough = False` set first so the callback actually fires (see Files module docs for the underlying Werkzeug behavior). Async app-data export uses the shared jobs registry; its inner `_run()` closure is exercised directly in tests for both the success and cleanup-on-failure paths.

## Known Limitations

- These are `GET` routes that perform privileged/exporting actions. They remain login-protected and audited by design; this is an accepted tradeoff, not a code bug, but accidental prefetching should still be kept in mind for any new export route.

## Testing

- `tests/test_backup.py`
- `tests/test_backup_routes.py`
- Coverage: 100% backend, 94% route

See [`docs/module-audits/backup.md`](../module-audits/backup.md) for the audit history (bugs found and fixed, and any items still open).
