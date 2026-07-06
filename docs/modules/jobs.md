# Jobs

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Shared in-memory background-job registry used by every module's async (long-running) operations -- APK installs, large pulls/exports -- with progress reporting and cancellation.

## Files

- `adb/jobs.py`
- `routes/jobs.py`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/jobs` | List recent jobs (most recent 50). |
| GET | `/api/jobs/<job_id>` | Get one job's public state. |
| POST | `/api/jobs/<job_id>/cancel` | Cancel a pending/running job. |
| GET | `/api/jobs/<job_id>/download` | Download a completed job's result file. |

## Behavior

- In-memory background job registry with pending/running/done/error/cancelled states.
- Supports public job snapshots, cancellation events, subprocess termination, background execution, progress parsing from `NN%`, and result downloads.
- `run_adb_with_progress()` streams subprocess output, checks the cancel event and an optional timeout on every line, and parses `NN%` occurrences into job progress (best-effort; absence of a match just leaves progress indeterminate).
- The result-download route checks `Path(file_path).is_file()` before calling `send_file()`, returning `{"ok": false, "error": "result_file_missing"}` with **410 Gone** for a stale or already-cleaned-up result file, instead of letting an unhandled `FileNotFoundError` surface as a raw 500. It also sets `response.direct_passthrough = False` before `call_on_close()`, the same fix described in the Files module docs.
- `create_job()` prunes the registry down to `_MAX_RETAINED_JOBS` (200) after every insert, dropping the oldest **terminal** (`done`/`error`/`cancelled`) jobs first. Pending/running jobs are never pruned, regardless of how far over the cap the registry gets, so a caller polling or cancelling a job it knows is in flight can never have it disappear underneath it.

## Known Limitations

- Jobs are process-local; registry state does not survive a server restart. An accepted tradeoff for a local single-user tool.

## Testing

- `tests/test_jobs.py`
- `tests/test_jobs_routes.py`
- Coverage: 90% backend, 100% route

See [`docs/module-audits/jobs.md`](../module-audits/jobs.md) for the audit history (bugs found and fixed, and any items still open).
