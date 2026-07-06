# Files Audit

Files: `adb/files.py`, `routes/files.py`, `static/js/files.js`

Coverage: backend 36%, route 24%.

## Implementation

- Supports browse, search, mkdir, delete, rename, move, copy, upload, preview, file download, folder download, and async folder download.
- Shell path arguments are quoted with `manager.quote_remote()` in the backend for browse/search/CRUD/preview commands.
- Host-side uploads use `secure_filename()` and temporary directories under `config.TEMP_DIR`.
- Download routes clean temporary directories with Flask `call_on_close()`; async jobs return result metadata for the jobs download endpoint.

## Verified

- `ls -la` parser is covered for directories, files, symlinks, garbled fallback lines, and ignored total/blank lines.
- Preview kind classification is covered.

## Gaps And Risks

- Route coverage is low for a large surface area with file exfiltration and mutation.
- Async folder downloads rely on job cleanup after result download. Interrupted clients may leave temp directories until process cleanup/manual deletion.
- Search queries are quoted, but `find` behavior and permission-denied partial output are not mocked in tests.
- Upload route checks request content length before saving, but file type and APK/device storage limits are outside its scope.

## Recommended Tests

- Mocked route tests for every mutating endpoint with and without CSRF.
- Command-construction tests for paths containing spaces, quotes, wildcards, and shell metacharacters.
- Temp cleanup tests for preview/download success and error paths.
- Async job tests for folder download success, failure, cancellation, and job-result download cleanup.
