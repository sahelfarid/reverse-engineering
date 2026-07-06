# Core, Auth, Config, Desktop Audit

Files: `app.py`, `auth.py`, `config.py`, `desktop.py`, `routes/core.py`

Coverage: app 55%, auth 68% (was 62%), config 92% (was 83%), desktop 57% (was 44%), routes/core 66% (was 55%).

## Implementation

- `app.create_app()` uses `config.TEMPLATE_DIR` and `config.STATIC_DIR`, which keeps Flask asset lookup compatible with PyInstaller bundles.
- Auth is single-user session auth with generated first-run password, Werkzeug password hashing, CSRF token generation, and a JSON-lines audit log.
- Mutating core endpoints require login and CSRF: change password, install ADB, update settings. Public `/api/adb/status` remains unauthenticated for startup checks.
- `config.py` separates read-only bundled assets from writable data. Frozen builds write state to per-user app data rather than PyInstaller extraction directories.
- `desktop.py` provides free-port selection, readiness polling, a single-instance lock, and pywebview startup.
- `config.validate_settings_patch()` is a new allowlist/range validator: each settings key has an explicit type/range check (`refresh_interval_ms` 250-60000, `shell_timeout_sec` 1-300, `max_log_lines` 100-200000, `max_upload_mb` 1-4096, `theme` in `dark`/`light`, path-like strings for `adb_path_override`/`default_device_serial`/`download_dir`). Unknown keys, wrong types (including `bool` sneaking in through Python's `int` subclassing), and out-of-range values are rejected per-key rather than failing the whole request. `password_hash` is always rejected here; it can only be set via the change-password flow.
- `routes/core.update_settings()` now calls that validator, saves only the accepted keys, and returns a `rejected` list in the response (and in the audit log details) instead of silently accepting or writing anything sent by the client.

## Verified

- Login page/API auth gating, invalid and valid login, and CSRF rejection are covered by `tests/test_app_routes.py`.
- Frozen path helpers, per-OS user data paths, free-port selection, and lock-file behavior are covered by `tests/test_portable.py`.
- `config.validate_settings_patch()` is covered in `tests/test_config.py` for: accepting known in-range values, rejecting `password_hash`, rejecting unknown keys, rejecting out-of-range values, rejecting wrong types (string where int expected, `bool` where `int` expected, `float` where `int` expected), and partial success (good keys kept, bad keys reported, nothing raises).
- `config.load_settings()` corrupt-JSON recovery (falls back to defaults) and default-merge behavior are covered in `tests/test_config.py`.
- `config.generate_secret_key()` persistence across calls and hex-token shape are covered in `tests/test_config.py`.
- `POST /api/settings` is covered end-to-end in `tests/test_app_routes.py` for accepting valid keys, reporting `rejected` for unknown/out-of-range keys, and never leaking/accepting `password_hash` through this endpoint.
- `desktop.wait_until_ready()` is covered for both the ready-on-200 and timeout-without-ready paths (mocked `urllib.request.urlopen`). `desktop.main()`'s existing-instance short-circuit is covered.
- Full test suite passed: 95 tests.

## Gaps And Risks

- `auth.audit_log()` assumes a valid request context in normal use. That is fine for routes, but direct background-job calls should avoid using it outside Flask request context.
- The pywebview-window and browser-fallback branches of `desktop.main()` are still not integration-tested; they run an OS-level window/`webbrowser.open()` and, in the no-pywebview fallback, an indefinite loop, which makes them awkward to exercise safely in a unit test. The existing-lock short-circuit and readiness polling are covered instead.

## Recommended Tests

- Flask client tests for change-password success/failure and ADB install error paths (settings sanitization and audit-log visibility are now covered).
- A `desktop.main()` test that mocks the `webview` module import to assert `create_window`/`start` are called with the expected URL, without actually opening a window.
