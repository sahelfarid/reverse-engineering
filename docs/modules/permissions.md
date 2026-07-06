# Permissions

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Reads and classifies an app's Android permissions, and grants/revokes them.

## Files

- `adb/permissions.py`
- `permission routes in routes/battery.py`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices/<serial>/packages/<package>/permissions` | Permission detail (requested/granted/denied, dangerous classification). |
| POST | `/api/devices/<serial>/packages/<package>/permissions/grant` | Grant a permission. |
| POST | `/api/devices/<serial>/packages/<package>/permissions/revoke` | Revoke a permission. |

## Behavior

- Validates permission strings, classifies dangerous permissions, reads package permissions through the App Inspector module, and grants/revokes permissions with `pm grant`/`pm revoke`.
- Package and permission values are validated before shell use and quoted in grant/revoke commands.
- Grant/revoke routes require login, CSRF, and audit logging.
- `grant_permission()`/`revoke_permission()` fall back to `stdout` when `stderr` is empty, since some Android/OEM `pm` builds print failure text (e.g. `Failure: SecurityException`) to stdout rather than stderr.

## Known Limitations

- `_PERMISSION_RE` intentionally allows broad custom permission names, to support app-defined permissions.
- Permission detail depends on the App Inspector module's `dumpsys package` scraping, which remains best-effort for OEM format variance.

## Testing

- `tests/test_permissions.py`
- `tests/test_permissions_routes.py`
- Coverage: 100% backend, 100% route

See [`docs/module-audits/permissions.md`](../module-audits/permissions.md) for the audit history (bugs found and fixed, and any items still open).
