# Core, Auth, Config, Desktop Audit

Files: `app.py`, `auth.py`, `config.py`, `desktop.py`, `routes/core.py`

Coverage: app 55%, auth 68%, config 92%, desktop 78% (was 57%), routes/core 90% (was 66%).

Full implementation notes, API reference, and permanent known limitations now live in the module
documentation: [`docs/modules/core-auth-config-desktop.md`](../modules/core-auth-config-desktop.md). This file tracks only what is still
open from the original audit pass.

## Resolved This Pass

Added Flask-client tests for `/api/auth/change-password` (wrong current password, too-short new password, success + audit log + old-password invalidation, CSRF rejection) and `/api/adb/install` (success + audit log, `AdbInstallError` -> 500), plus `desktop.main()` tests that mock the `webview` import to assert `create_window`/`start` are called with the expected URL, and that the no-pywebview branch falls back to `webbrowser.open()`. These were the last recommended-test gaps for this module.

## Remaining Items

- None. Every gap and recommended test identified in the original audit has been closed -- either fixed in code (with a regression test proving the bug existed) or closed with test coverage where the gap was purely a testing hole. See the module documentation's Known Limitations section for the permanent, accepted tradeoffs that remain by design (not bugs).
