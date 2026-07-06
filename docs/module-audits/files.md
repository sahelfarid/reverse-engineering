# Files Audit

Files: `adb/files.py`, `routes/files.py`, `static/js/files.js`

Coverage: backend 98%, route 95% (was 89% -- closed by the async-closure tests below).

Full implementation notes, API reference, and permanent known limitations now live in the module
documentation: [`docs/modules/files.md`](../modules/files.md). This file tracks only what is still
open from the original audit pass.

## Resolved This Pass

Added direct tests for the async folder-download job's inner `_run()` closure -- previously only the outer route wiring (`create_job`/`run_in_background` call) was covered. The closure is now exercised for both the success path (progress callback + zip result) and the cleanup-on-failure path (`adb is not installed` mid-closure -> temp dir removed).

## Remaining Items

- None. Every gap and recommended test identified in the original audit has been closed -- either fixed in code (with a regression test proving the bug existed) or closed with test coverage where the gap was purely a testing hole. See the module documentation's Known Limitations section for the permanent, accepted tradeoffs that remain by design (not bugs).
