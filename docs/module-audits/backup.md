# Backup Audit

Files: `adb/backup.py`, `routes/backup.py`, `static/js/backup.js`

Coverage: backend 100% (was 19%), route 89% (was 30%).

## Implementation

- Exports common media folders, logcat dumps, APKs, app databases, and app data archives.
- Database and app-data exports validate package names through `adb.packages.validate_package()`.
- Database names reject `/`, `.`, and `..`.
- App-data export tries `run-as` first and root fallback second, then pulls a temporary archive and removes the remote temp file.
- Download routes clean local temp directories via `call_on_close()`. Async app-data exports use the shared jobs registry.

## Verified

- `resolve_export_path()`, `dump_logcat_to_file()` (including wireless-serial filename sanitization), `export_database()` (unsafe-name rejection, run-as success, root fallback, inaccessible case), and `export_app_data()` (run-as success + cleanup command, root fallback + cleanup command, inaccessible case, and the root-tar-failure case below) are all covered directly.
- Every route is covered: `targets`, `export_folder` (unknown target 404, success + cleanup + audit log, pull failure), `export_logcat`/`export_apk`/`export_database`/`export_app_data` (success + cleanup + audit log, missing-field 400s), and `export_app_data_async` (job creation, missing-package 400).

**Two real bugs found and fixed while writing these tests:**
1. `export_app_data()` discarded the root-tar fallback command's return code entirely (`manager.shell(serial, f"su 0 tar -czf ...")` with no assignment). A failing root tar (e.g. permission denied) fell straight through to `adb_files.pull_file()`, surfacing as a confusing "pull failed" error instead of the actual tar failure. Now captures the return code and raises `AdbError(f"root tar failed: {stderr}")` immediately, matching the pattern already used for the run-as attempt. Verified by reverting the fix and confirming the new test attempts a real (unmocked) `pull_file()` call instead of stopping early.
2. All five backup download routes shared `_send_and_cleanup()`, which had the same `send_file()`/`direct_passthrough` cleanup bug as `routes/files.py`, `routes/packages.py`, and `routes/screen.py`: `call_on_close()` never fired, so every folder/logcat/APK/database/app-data export leaked its temp directory. Fixed once in the shared helper (`response.direct_passthrough = False`), covering all five routes at once. Verified by reverting and confirming `test_export_logcat_success_cleans_up` fails without it.

## Gaps And Risks

- GET routes perform privileged/exporting actions. They remain login-protected and audited (as before); HTTP semantics mean accidental prefetching should still be kept in mind, but this is an accepted, documented tradeoff rather than a code bug.
- The async app-data export job's inner `_run()` closure is not directly tested here, same as the async folder-download closure in `routes/files.py` -- tracked together with the Jobs module pass.

## Recommended Tests

- Async job tests for app-data export success/failure/cancel, covered together with the Jobs module's `run_adb_with_progress()` tests.
