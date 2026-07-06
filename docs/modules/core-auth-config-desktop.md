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
| GET | `/` | First-launch setup screen, login page, or dashboard, depending on auth state. |
| POST | `/api/auth/setup` | First-launch only: optionally set a password (or skip), with "remember me". Logs in immediately. |
| POST | `/api/auth/login` | Password login, with a "remember me" option; issues a CSRF token on success. |
| POST | `/api/auth/logout` | End the session. |
| POST | `/api/auth/change-password` | Change the login password; requires current password (unless none is set yet) + CSRF. |
| POST | `/api/auth/reset` | Forgot-password recovery: clears the password and rotates the session-signing key, invalidating every remembered session everywhere. Requires `{"confirm": true}`; deliberately reachable without login. |
| GET | `/api/adb/status` | Unauthenticated ADB install/version status, for startup checks. |
| POST | `/api/adb/install` | Download and install bundled platform-tools. |
| GET | `/api/settings` | Read current settings (password hash stripped). |
| POST | `/api/settings` | Patch settings against the per-key validator. |
| GET | `/api/audit` | Read the JSON-lines audit log. |

## Behavior

- `app.create_app()` uses `config.TEMPLATE_DIR` and `config.STATIC_DIR`, which keeps Flask asset lookup compatible with PyInstaller bundles. It also sets `app.permanent_session_lifetime` to 30 days, which only takes effect for sessions marked `permanent` (the "remember me" option) -- a normal login stays a browser-session cookie that ends when the browser closes.
- Auth is single-user session auth with Werkzeug password hashing, CSRF token generation, and a JSON-lines audit log. There is no automatic random first-run password anymore: `index()` serves a first-launch **setup screen** (`templates/setup.html`) whenever `auth.is_setup_complete()` is false, where the user either sets a password (min 6 chars) or explicitly skips it.
- **A skipped password means open access by design**: `auth.is_authenticated()` returns `True` unconditionally once setup is complete and no password is set, for every client, with or without a session. This is a deliberate, reversible choice for solo local use -- add a password anytime from Settings (`change_password()` allows setting an initial one with no `current_password` when none exists yet), or reset from the login page.
- Because open-access mode never calls `login_session()` (which normally issues the CSRF token), `index()` calls `auth.ensure_csrf_token()` before rendering the dashboard so mutating routes stay reachable even when nobody ever "logged in".
- The login page's **"Forgot password? Reset"** link (after a `confirm()` dialog) hits `POST /api/auth/reset`, which clears `password_hash`, sets `auth_setup_complete` back to `False` (showing the setup screen again), and calls `config.regenerate_secret_key()` + updates `current_app.secret_key` live -- rotating the Flask session-signing key immediately invalidates every outstanding session/remember-me cookie everywhere, not just the browser that requested the reset, since a Flask cookie session is only as valid as its signature. This route is intentionally reachable without a session or CSRF token (that's the point of a reset); it requires an exact `{"confirm": true}` body instead, and a JSON POST from another origin can't reach it without a CORS preflight this app never grants.
- Mutating core endpoints require login and CSRF: change password, install ADB, update settings. The public `/api/adb/status` stays unauthenticated so the UI can show install status before login; `/api/auth/setup` and `/api/auth/reset` are also intentionally unauthenticated, each for its own pre-login reason above.
- `config.py` separates read-only bundled assets from writable data; frozen (PyInstaller) builds write state to per-user app-data directories rather than the extraction directory.
- `config.validate_settings_patch()` is an allowlist/range validator: each settings key has an explicit type/range check (`refresh_interval_ms` 250-60000, `shell_timeout_sec` 1-300, `max_log_lines` 100-200000, `max_upload_mb` 1-4096, `theme` in `dark`/`light`, path-like strings for `adb_path_override`/`default_device_serial`/`download_dir`). Unknown keys, wrong types (including `bool` sneaking in through Python's `int` subclassing), and out-of-range values are rejected per-key rather than failing the whole request. `password_hash` and `auth_setup_complete` are always rejected here; they can only be set via the setup/change-password/reset flows.
- `desktop.py` provides free-port selection, readiness polling against `/api/adb/status`, a single-instance lock file (PID + port, with a live-connect probe to detect stale locks), and pywebview startup with a default-browser fallback when pywebview isn't installed.

## Known Limitations

- `auth.audit_log()` assumes a valid Flask request context in normal use. That's fine for routes, but background-job code should avoid calling it directly outside of one.
- Open-access mode (password skipped) applies to every route on the loopback-bound server -- there's no partial/read-only mode. Anyone with local access to the machine while the app is running has full access, same as if they knew the password. This is the explicit tradeoff of making the password optional for a single-user local tool.
- The password-reset flow has no rate limiting or additional local proof beyond the confirmation dialog -- appropriate for a loopback-only single-user tool, but worth remembering if this app's trust model ever changes (e.g. binding beyond `127.0.0.1`, which the rest of this codebase already treats as out of scope).

## Testing

- `tests/test_app_routes.py`
- `tests/test_auth_setup.py` -- first-launch setup screen (set password / skip), the open-access consequence of skipping, re-rejection once already configured, the reset flow (confirmation required, password + all sessions cleared), and remember-me cookie persistence.
- `tests/test_config.py`
- `tests/test_portable.py`
- Coverage: app 92%, auth 86%, config 92%, desktop 79%, routes/core 95%

See [`docs/module-audits/core-auth-config-desktop.md`](../module-audits/core-auth-config-desktop.md) for the audit history (bugs found and fixed, and any items still open).
