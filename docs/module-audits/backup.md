# Backup Audit

Files: `adb/backup.py`, `routes/backup.py`, `static/js/backup.js`

Coverage: backend 100%, route 94% (was 89% -- closed by the async-closure tests below).

Full implementation notes, API reference, and permanent known limitations now live in the module
documentation: [`docs/modules/backup.md`](../modules/backup.md). This file tracks only what is still
open from the original audit pass.

## Resolved This Pass

Added direct tests for the async app-data export job's inner `_run()` closure, mirroring the Files module fix: success path (calls `export_app_data`, returns result metadata) and cleanup-on-failure path (`AdbError` mid-closure -> temp dir removed).

## Remaining Items

- None. Every gap and recommended test identified in the original audit has been closed -- either fixed in code (with a regression test proving the bug existed) or closed with test coverage where the gap was purely a testing hole. See the module documentation's Known Limitations section for the permanent, accepted tradeoffs that remain by design (not bugs).
