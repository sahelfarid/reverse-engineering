# Jobs Audit

Files: `adb/jobs.py`, `routes/jobs.py`

Coverage: backend 90%, route 100% (unchanged -- the new pruning code is fully covered by its own tests).

Full implementation notes, API reference, and permanent known limitations now live in the module
documentation: [`docs/modules/jobs.md`](../modules/jobs.md). This file tracks only what is still
open from the original audit pass.

## Resolved This Pass

Implemented an actual pruning policy: `create_job()` now caps the registry at `_MAX_RETAINED_JOBS`
(200), dropping the oldest terminal (`done`/`error`/`cancelled`) jobs first once the cap is
exceeded. Pending/running jobs are never pruned. Covered by two new tests:
`test_prune_drops_oldest_terminal_jobs_beyond_cap` and
`test_prune_never_removes_pending_or_running_jobs`. This closes the item that the previous pass
left open pending a real retention feature -- there's now a real feature and real tests instead of
an open question.

## Remaining Items

- None. Every gap and recommended test identified in the original audit has been closed -- either fixed in code (with a regression test proving the bug existed) or closed with test coverage where the gap was purely a testing hole. See the module documentation's Known Limitations section for the permanent, accepted tradeoffs that remain by design (not bugs).
