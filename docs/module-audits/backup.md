# Backup Audit

Files: `adb/backup.py`, `routes/backup.py`, `static/js/backup.js`

Coverage: backend 19%, route 30%.

## Implementation

- Exports common media folders, logcat dumps, APKs, app databases, and app data archives.
- Database and app-data exports validate package names through `adb.packages.validate_package()`.
- Database names reject `/`, `.`, and `..`.
- App-data export tries `run-as` first and root fallback second, then pulls a temporary archive and removes the remote temp file.
- Download routes clean local temp directories via `call_on_close()`. Async app-data exports use the shared jobs registry.

## Verified

- Coverage is mostly indirect through package/file/job tests.

## Gaps And Risks

- Low coverage for a high-value data exfiltration module.
- `export_app_data()` does not check the root tar command return code before pulling; a failed root tar may surface later as a pull failure, but a clearer error would help.
- GET routes perform privileged/exporting actions. They are login-protected and audited, but HTTP semantics mean accidental prefetching should be considered.
- Temp cleanup depends on response close or jobs download.

## Recommended Tests

- Unit tests for common target resolution, logcat dump write, database name rejection, run-as/root fallback, remote cleanup, and root tar failure.
- Route tests for missing fields, unknown targets, ADB errors, audit logging, and temp cleanup.
- Async job tests for app-data export success/failure/cancel.
