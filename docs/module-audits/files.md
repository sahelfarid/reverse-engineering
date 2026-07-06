# Files Audit

Files: `adb/files.py`, `routes/files.py`, `static/js/files.js`

Coverage: backend 98% (was 36%), route 89% (was 24%).

## Implementation

- Supports browse, search, mkdir, delete, rename, move, copy, upload, preview, file download, folder download, and async folder download.
- Shell path arguments are quoted with `manager.quote_remote()` in the backend for browse/search/CRUD/preview commands.
- Host-side uploads use `secure_filename()` and temporary directories under `config.TEMP_DIR`.
- Download routes clean temporary directories with Flask `call_on_close()`; async jobs return result metadata for the jobs download endpoint.

## Verified

- `ls -la` parser is covered for directories, files, symlinks, garbled fallback lines, and ignored total/blank lines.
- Preview kind classification is covered.
- `list_directory()`, `search_path()`, `mkdir_path()`/`delete_path()`/`move_path()`/`copy_path()`/`rename_path()`, `pull_file()` (including single-candidate fallback and multi-candidate/missing-file failure), `push_file()`, `read_text_preview()`, and `zip_folder()` are all covered for success and failure paths with a mocked `manager.shell()`/`manager.run()`.
- Every mutating route (`mkdir`, `delete`, `rename`, `move`, `copy`, `upload`) is covered for missing-field 400s, success, audit-log details, and `AdbError`/`AdbNotInstalledError` mapping. `upload` is covered for `missing_file` and `file_too_large` (413).
- `browse`/`search`/`preview`/`download`/`download-folder` are covered for missing-path 400s, success, and `not ok` -> 404 (`browse`).
- `download-folder` and `download-folder/async` are covered for missing-path, pull-failure mapping, zip creation, and (for the sync route) temp-dir cleanup + audit log.

**A real bug found and fixed while writing these tests:** `preview()`, `download()`, and `download_folder()` all built their `send_file()` response and then registered cleanup via `response.call_on_close(...)`. `send_file()` sets `direct_passthrough=True`, and Werkzeug's `Response.get_app_iter()` returns the raw file wrapper directly in that mode -- skipping the `ClosingIterator(iterable, self.close)` wrapper that is the *only* thing that ever invokes `Response.close()` (and therefore the registered `call_on_close` callbacks). Concretely: **the temp directories created for every image preview, file download, and folder download were never being deleted, on any WSGI server, not just interrupted clients.** Fixed by setting `response.direct_passthrough = False` right before registering the callback in all three routes; verified by reverting the fix locally and confirming `tests/test_files_routes.py::test_preview_image_kind_pulls_and_cleans_up` and `::test_download_success_cleans_up_temp_dir` fail without it.

## Gaps And Risks

- The async folder-download job's inner `_run()` closure (the part that actually calls `run_adb_with_progress()` and zips the result) is still untested -- it runs on a background thread via `adb_jobs.run_in_background()`, which is mocked out rather than executed in the route tests. Job success/failure/cleanup for this closure should be covered alongside the Jobs module tests.
- Search queries are quoted, but real `find` behavior on minimal/OEM Android environments (partial permission-denied output) remains a best-effort assumption, same as before.
- Upload route checks request content length before saving, but file type and APK/device storage limits are outside its scope (unchanged from original audit; not a bug, a documented scope boundary).

## Recommended Tests

- Async job tests for the folder-download `_run()` closure itself: success, `run_adb_with_progress()` failure, and cleanup on exception. `run_adb_with_progress()` itself is now covered by the Jobs module pass; the closure that calls it here is still route-level untested (mocked out via `run_in_background()` in the route tests).
- The same `direct_passthrough` fix was needed (and has since been applied) in `routes/backup.py`, `routes/packages.py`, `routes/jobs.py`, and `routes/screen.py`, which use the identical `send_file()` + `call_on_close()` pattern -- see each module's own audit file for details.
