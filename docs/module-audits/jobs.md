# Jobs Audit

Files: `adb/jobs.py`, `routes/jobs.py`

Coverage: backend 90% (was 61%), route 100% (was 50%).

## Implementation

- In-memory background job registry with pending/running/done/error/cancelled states.
- Supports public job snapshots, cancellation events, subprocess termination, background execution, progress parsing from `NN%`, and result downloads.
- Result download route can clean temp directories when the response closes.

## Verified

- Job lifecycle success, cancel-before-run, idempotent cancel after completion, and error capture are covered.
- `run_adb_with_progress()` is covered for progress-percentage parsing with consecutive-duplicate dedup, `set_job_process()` wiring, nonzero-exit -> `AdbError`, mid-stream cancellation (`terminate()` called, `JobCancelled` raised), timeout -> `AdbError` (`terminate()` called), and cancellation detected only after the subprocess has already exited (post-`wait()` check, no `terminate()` needed).
- Every route is covered: `list`, `get` (found/not-found), `cancel` (success + CSRF rejection), and `download` (not-ready when missing/not-done, the stale-file case below, success with temp cleanup, success without a `tmp_dir` skipping cleanup, and login-required 401).

**Two real bugs found and fixed while writing these tests:**
1. `download_job_result()` only checked the job's public status/result fields, not whether the result file still existed on disk. A stale or already-cleaned-up file made `send_file()` raise an unhandled `FileNotFoundError`, surfacing as a raw Werkzeug 404/500 page instead of a clean JSON error. Now checks `Path(file_path).is_file()` first and returns `{"ok": false, "error": "result_file_missing"}` with **410 Gone**. Verified by reverting and confirming the new test hits an unhandled `FileNotFoundError`.
2. Same `send_file()`/`direct_passthrough` cleanup bug as the other download routes: `call_on_close()` never fired, so job-result downloads with a `tmp_dir` never cleaned up. Fixed with `response.direct_passthrough = False`. This was the last of the five routes flagged with this bug across the app (`routes/files.py`, `routes/packages.py`, `routes/screen.py`, `routes/backup.py`, `routes/jobs.py` -- all now fixed).

## Gaps And Risks

- Jobs are process-local and not pruned except by the 50-item list view limit. Long-running sessions can accumulate registry state; this is a documented, accepted tradeoff for a local single-user tool, unchanged from the original audit.

## Recommended Tests

- Optional pruning policy tests if retention limits are added in the future.
