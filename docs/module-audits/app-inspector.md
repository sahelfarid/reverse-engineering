# App Inspector Audit

Files: `adb/app_inspector.py`, `routes/app_inspector.py`, `static/js/inspector.js`

Coverage: backend 100% (was 13%), route 96% (was 46%).

## Implementation

- Gathers requested/granted/denied permissions, CPU ABI values, exported-ish component references from global `dumpsys package`, and app data/database/shared preference visibility.
- Package names are validated through `adb.packages.validate_package()`.
- Data access attempts `run-as` first and root fallback second.
- Restart route delegates to package restart and is CSRF-protected and audit-logged.

## Verified

- `get_permissions()` is covered for requested/granted/denied extraction plus CPU ABI fields, and for the shell-failure empty-result path.
- `get_components()` is covered for extracting all four resolver-table kinds, shell failure, and a missing-section (no match) case.
- `get_data_dirs()` is covered for the `run-as`-accessible path, the root-fallback path (`run-as` fails, `su -c` succeeds), and the inaccessible case (no `run-as`, no root).
- `get_app_detail()` is covered as a pure composer over the three functions above.
- `routes/app_inspector.py` is covered end-to-end for `inspect` (success, `AdbNotInstalledError` -> 503, `AdbError` -> 400, login-required) and `restart` (CSRF rejection, success + audit log, `AdbError` -> 400).

**A real bug found and fixed while writing these tests:** `get_permissions()`'s "requested permissions" regex used `\n?` (optional trailing newline) per captured entry, so on real device output -- where the `install permissions:` section header immediately follows `requested permissions:` with no blank line, which is the normal Android format -- the parser's greedy `[\w.]+` matching bled into the next line, appending a bogus `"install permissions"` string to the `requested` permissions list. Fixed by making the trailing `\n` mandatory per entry, which stops the match cleanly at the section boundary. Caught by `test_get_permissions_parses_requested_and_granted_state`, which failed against the original regex with exactly that fixture.

## Gaps And Risks

- `get_components()` scans global `dumpsys package` output and may still include false positives or miss components on OEM-specific formats; this is a documented best-effort limitation, not something unit tests against a single fixture can fully rule out.
- Root fallback in `get_data_dirs()` builds `f"su -c '{cmd_suffix}'"` without `manager.quote_remote()` around the whole command, but `cmd_suffix` is built only from an already-validated package name (via `packages.validate_package()`) and static strings, so there's no user-controlled injection surface here.

## Recommended Tests

- None outstanding for this module's Python surface; remaining gaps are OEM dumpsys-format variance, which needs real-device/emulator smoke testing rather than more mocked unit tests.
