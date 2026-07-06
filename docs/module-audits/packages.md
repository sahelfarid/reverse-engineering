# Packages Audit

Files: `adb/packages.py`, `routes/packages.py`, `static/js/packages.js`

Coverage: backend 99% (was 39%), route 91% (was 35%).

## Implementation

- Supports package listing, APK path and size lookup, install/install-multiple, uninstall, disable, enable, clear data, force-stop, launch, restart, and APK pull.
- Package names are validated with a strict Java-style package regex before shell use.
- Installs use host argv-list ADB calls. PM actions quote package names before device shell commands.
- Routes require login and CSRF for mutations. APK pull is read-only in HTTP method terms but audit-logged because it exports device data.

## Verified

- Dumpsys package parser is covered for multi-package extraction and empty input.
- Package validation accepts normal names and rejects shell metacharacters.
- `list_packages()` is covered for the dumpsys path, the `pm list packages -f` fallback, and the failure-to-list case (raises `AdbError`).
- `get_apk_path()`, `get_apk_size()`, `install_apk()`, `install_multiple_apks()` (argv construction), `uninstall_apk()` (`-k` flag), the `_pm_action`-based helpers (`disable_package`/`enable_package`/`clear_data`), `force_stop()`, `launch_app()` (including the "no activities" failure case), and `restart_app()` (delegates to `force_stop` then `launch_app`) are all covered.
- `pull_apk()` is covered for the success/rename path, unresolved APK path, ADB pull failure, and the missing-pulled-file case below.
- Routes are covered end-to-end for list/size/install (single + multiple files)/install-async/uninstall/all five PM action routes/pull, including CSRF-gated audit-log assertions and `AdbError`/`AdbNotInstalledError` mapping.

**A real bug found and fixed while writing these tests:** `pull_apk()` fell through to `return pulled_name` even when `pulled_name.exists()` was `False` -- i.e. when `adb pull` reported success but the file didn't land where expected (unusual device/adb output), callers received a `Path` to a file that doesn't exist, which `routes/packages.py`'s `send_file()` would only discover deep inside Werkzeug's file-opening logic with a much less clear error. Fixed to raise `AdbError("pulled apk not found in destination directory for {package}")` in that case instead.

**Same `send_file` + `call_on_close` cleanup bug as `routes/files.py`:** `pull_apk()`'s route registered temp-dir cleanup via `call_on_close()` after a `send_file()` call, which never fires because of `direct_passthrough=True` (see `docs/module-audits/files.md` for the full explanation). Fixed the same way: `response.direct_passthrough = False` before registering the callback.

## Gaps And Risks

- Version parsing is best-effort and depends on Android `dumpsys` format (unchanged; documented limitation, not a bug).
- `_make_action_route()` binds each PM action's backend function into a closure at blueprint-registration (import) time. This is normal and correct for production, but it means route tests must patch at `manager.shell()` rather than at the `adb_packages.<fn>` name -- noted in the test file so this isn't rediscovered as a false "route doesn't call the mock" bug.

## Recommended Tests

- The same `direct_passthrough` regression check applied to `routes/backup.py`, `routes/jobs.py`, and `routes/screen.py` (tracked in `docs/module-audits/files.md`).
