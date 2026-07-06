# App Inspector Audit

Files: `adb/app_inspector.py`, `routes/app_inspector.py`, `static/js/inspector.js`

Coverage: backend 13%, route 46%.

## Implementation

- Gathers requested/granted/denied permissions, CPU ABI values, exported-ish component references from global `dumpsys package`, and app data/database/shared preference visibility.
- Package names are validated through `adb.packages.validate_package()`.
- Data access attempts `run-as` first and root fallback second.
- Restart route delegates to package restart and is CSRF-protected and audit-logged.

## Verified

- Coverage is mostly indirect through package validation tests and route registration.

## Gaps And Risks

- Backend parser coverage is very low for a module that depends heavily on Android dumpsys formatting.
- `get_components()` scans global `dumpsys package` output and may include false positives or miss components on OEM-specific formats.
- Root fallback in `get_data_dirs()` is command-string sensitive. Current package validation makes the interpolated package safe, but mocked command tests should lock this down.

## Recommended Tests

- Parser fixtures for `dumpsys package <pkg>` permission blocks and CPU ABI lines.
- Component extraction tests for activity/service/receiver/provider sections.
- `run-as` success, root fallback success, and inaccessible app-data tests.
- Flask client tests for inspect/restart success and ADB error mapping.
