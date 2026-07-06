# Jobs Audit

Files: `adb/jobs.py`, `routes/jobs.py`

Coverage: backend 61%, route 50%.

## Implementation

- In-memory background job registry with pending/running/done/error/cancelled states.
- Supports public job snapshots, cancellation events, subprocess termination, background execution, progress parsing from `NN%`, and result downloads.
- Result download route can clean temp directories when the response closes.

## Verified

- Job lifecycle success, cancel-before-run, idempotent cancel after completion, and error capture are covered.

## Gaps And Risks

- `run_adb_with_progress()` is not tested. This is the function that manages live subprocesses, progress parsing, timeout, and cancellation.
- Jobs are process-local and not pruned except by the 50-item list view limit. Long-running sessions can accumulate registry state.
- Download route only checks public job result fields; stale file paths return send-file errors rather than a structured JSON error.

## Recommended Tests

- Mocked `subprocess.Popen` tests for progress updates, timeout, nonzero exit, cancellation, and process termination errors.
- Route tests for list/get/cancel/download including not-found, not-ready, stale file, and cleanup behavior.
- Optional pruning policy tests if retention limits are added.
