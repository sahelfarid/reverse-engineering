# Core, Auth, Config, Desktop Audit

Files: `app.py`, `auth.py`, `config.py`, `desktop.py`, `routes/core.py`

Coverage: app 92%, auth 86%, config 92%, desktop 79%, routes/core 95%.

Full implementation notes, API reference, and permanent known limitations now live in the module
documentation: [`docs/modules/core-auth-config-desktop.md`](../modules/core-auth-config-desktop.md). This file tracks only what is still
open from the original audit pass.

## Resolved This Pass

Added Flask-client tests for `/api/auth/change-password` (wrong current password, too-short new password, success + audit log + old-password invalidation, CSRF rejection) and `/api/adb/install` (success + audit log, `AdbInstallError` -> 500), plus `desktop.main()` tests that mock the `webview` import to assert `create_window`/`start` are called with the expected URL, and that the no-pywebview branch falls back to `webbrowser.open()`. These were the last recommended-test gaps for this module.

## Feature Added: Optional First-Launch Password, Remember Me, Password Reset

Replaced the automatic random first-run password (previously printed to stdout by `app.py`/`desktop.py`) with an interactive first-launch setup screen:

- `auth.is_setup_complete()` / `auth.has_password()` distinguish "never configured" from "configured, deliberately no password" -- `config.py`'s `DEFAULT_SETTINGS` gained an `auth_setup_complete` key for this.
- `POST /api/auth/setup` (routes/core.py) handles the setup screen: sets a password (min 6 chars) or skips, always logs the caller in, and rejects being called again once already configured.
- Skipping the password makes `auth.is_authenticated()` return `True` unconditionally (open access) -- `auth.ensure_csrf_token()` was added so mutating routes stay reachable in that mode even though `login_session()` (which normally issues the CSRF token) is never called.
- `auth.login_session()` and `POST /api/auth/login` gained a `remember` flag, backed by `session.permanent` + a new `app.permanent_session_lifetime = timedelta(days=30)` in `app.py`.
- `POST /api/auth/reset` (login page's "Forgot password? Reset" link, behind a `confirm()` dialog) clears the password and calls the new `config.regenerate_secret_key()`, updating `current_app.secret_key` live -- this rotates the Flask session-signing key, which invalidates every outstanding session/remember-me cookie everywhere immediately, not just the requesting browser. It's intentionally reachable without login (that's the point of a reset) but requires an exact `{"confirm": true}` body.
- `change_password()` now allows setting an initial password with no `current_password` when none exists yet (`auth.has_password()` gate), and re-establishes the session afterward so a previously open-access caller isn't locked out by their own change.
- New tests: `tests/test_auth_setup.py` (setup screen, skip-then-open-access, re-setup rejection, reset flow, remember-me cookie persistence, ensure_csrf_token's open-access branch) plus a new logout test in `tests/test_app_routes.py`.

## Remaining Items

- None. Every gap and recommended test identified in the original audit has been closed -- either fixed in code (with a regression test proving the bug existed) or closed with test coverage where the gap was purely a testing hole. See the module documentation's Known Limitations section for the permanent, accepted tradeoffs that remain by design (not bugs), including the open-access tradeoff and the reset flow's lack of rate limiting.
