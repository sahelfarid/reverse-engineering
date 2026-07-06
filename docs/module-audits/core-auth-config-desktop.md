# Core, Auth, Config, Desktop Audit

Files: `app.py`, `auth.py`, `config.py`, `desktop.py`, `routes/core.py`

Coverage: app 55%, auth 62%, config 83%, desktop 44%, routes/core 55%.

## Implementation

- `app.create_app()` uses `config.TEMPLATE_DIR` and `config.STATIC_DIR`, which keeps Flask asset lookup compatible with PyInstaller bundles.
- Auth is single-user session auth with generated first-run password, Werkzeug password hashing, CSRF token generation, and a JSON-lines audit log.
- Mutating core endpoints require login and CSRF: change password, install ADB, update settings. Public `/api/adb/status` remains unauthenticated for startup checks.
- `config.py` separates read-only bundled assets from writable data. Frozen builds write state to per-user app data rather than PyInstaller extraction directories.
- `desktop.py` provides free-port selection, readiness polling, a single-instance lock, and pywebview startup.

## Verified

- Login page/API auth gating, invalid and valid login, and CSRF rejection are covered by `tests/test_app_routes.py`.
- Frozen path helpers, per-OS user data paths, free-port selection, and lock-file behavior are covered by `tests/test_portable.py`.
- Full test suite passed: 71 tests.

## Gaps And Risks

- `routes/core.update_settings()` accepts arbitrary keys and value types except `password_hash`. Add schema/range validation for settings that affect process behavior, such as upload limits, refresh intervals, ADB overrides, and shell timeout.
- `auth.audit_log()` assumes a valid request context in normal use. That is fine for routes, but direct background-job calls should avoid using it outside Flask request context.
- Desktop startup and pywebview behavior are not integration-tested; tests cover pure lock/path/port helpers only.

## Recommended Tests

- Flask client tests for change-password success/failure, settings sanitization, audit log visibility, and ADB install error paths.
- Unit tests for malformed/corrupt `settings.json` recovery and `generate_secret_key()` persistence.
- A desktop smoke test that mocks `webview` and `requests.get()` readiness polling.
