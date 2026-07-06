# App Inspector Audit

Files: `adb/app_inspector.py`, `routes/app_inspector.py`, `static/js/inspector.js`

Coverage: backend 100%, route 96% (unchanged); now also exercised against a real device when one is attached (see below).

Full implementation notes, API reference, and permanent known limitations now live in the module
documentation: [`docs/modules/app-inspector.md`](../modules/app-inspector.md). This file tracks only what is still
open from the original audit pass.

## Resolved This Pass

Added `tests/test_app_inspector_smoke.py`, a real-device smoke test (gated by the shared
`real_device_serial` pytest fixture in `tests/conftest.py`) that runs `get_permissions()`,
`get_components()`, and `get_app_detail()` against a real, attached device's `android` system
package -- present on every real Android device/emulator, so the test needs no fixture install.
It skips cleanly with no authorized device attached (e.g. in CI). This closes the recommended
real-device follow-up from the original audit.

## Remaining Items

- None. Every gap and recommended test identified in the original audit has been closed -- either fixed in code (with a regression test proving the bug existed) or closed with test coverage where the gap was purely a testing hole. See the module documentation's Known Limitations section for the permanent, accepted tradeoffs that remain by design (not bugs).
