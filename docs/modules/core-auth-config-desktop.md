# Core, Auth, Config, Desktop

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Application bootstrap, single-user session authentication, on-disk configuration/settings management, and the optional native desktop (pywebview) shell around the Flask app.

## Files

- `app.py`
- `auth.py`
- `config.py`
- `desktop.py`
- `routes/core.py`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/` | Login page or dashboard, depending on auth state. |
| POST | `/api/auth/login` | Password login; issues a CSRF token on success. |
| POST | `/api/auth/logout` | End the session. |
| POST | `/api/auth/change-password` | Change the login password; requires current password + CSRF. |
| GET | `/api/adb/status` | Unauthenticated ADB install/version status, for startup checks. |
| POST | `/api/adb/install` | Download and install bundled platform-tools. |
| GET | `/api/settings` | Read current settings (password hash stripped). |
| POST | `/api/settings` | Patch settings against the per-key validator. |
| GET | `/api/audit` | Read the JSON-lines audit log. |

## Behavior

- `app.create_app()` uses `config.TEMPLATE_DIR` and `config.STATIC_DIR`, which keeps Flask asset lookup compatible with PyInstaller bundles.
- Auth is single-user session auth with a generated first-run password, Werkzeug password hashing, CSRF token generation, and a JSON-lines audit log.
- Mutating core endpoints require login and CSRF: change password, install ADB, update settings. The public `/api/adb/status` stays unauthenticated so the UI can show install status before login.
- `config.py` separates read-only bundled assets from writable data; frozen (PyInstaller) builds write state to per-user app-data directories rather than the extraction directory.
- `config.validate_settings_patch()` is an allowlist/range validator: each settings key has an explicit type/range check (`refresh_interval_ms` 250-60000, `shell_timeout_sec` 1-300, `max_log_lines` 100-200000, `max_upload_mb` 1-4096, `theme` in `dark`/`light`, path-like strings for `adb_path_override`/`default_device_serial`/`download_dir`). Unknown keys, wrong types (including `bool` sneaking in through Python's `int` subclassing), and out-of-range values are rejected per-key rather than failing the whole request. `password_hash` is always rejected here; it can only be set via the change-password flow.
- `desktop.py` provides free-port selection, readiness polling against `/api/adb/status`, a single-instance lock file (PID + port, with a live-connect probe to detect stale locks), and pywebview startup with a default-browser fallback when pywebview isn't installed.

## Known Limitations

- `auth.audit_log()` assumes a valid Flask request context in normal use. That's fine for routes, but background-job code should avoid calling it directly outside of one.

## Testing

- `tests/test_app_routes.py`
- `tests/test_config.py`
- `tests/test_portable.py`
- Coverage: app 55%, auth 68%, config 92%, desktop 78%, routes/core 90%

See [`docs/module-audits/core-auth-config-desktop.md`](../module-audits/core-auth-config-desktop.md) for the audit history (bugs found and fixed, and any items still open).
