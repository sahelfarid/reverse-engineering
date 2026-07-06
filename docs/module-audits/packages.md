# Packages Audit

Files: `adb/packages.py`, `routes/packages.py`, `static/js/packages.js`

Coverage: backend 39%, route 35%.

## Implementation

- Supports package listing, APK path and size lookup, install/install-multiple, uninstall, disable, enable, clear data, force-stop, launch, restart, and APK pull.
- Package names are validated with a strict Java-style package regex before shell use.
- Installs use host argv-list ADB calls. PM actions quote package names before device shell commands.
- Routes require login and CSRF for mutations. APK pull is read-only in HTTP method terms but audit-logged because it exports device data.

## Verified

- Dumpsys package parser is covered for multi-package extraction and empty input.
- Package validation accepts normal names and rejects shell metacharacters.

## Gaps And Risks

- Route upload/install paths are not covered, including multiple files, temp cleanup, and async install progress.
- `pull_apk()` returns `pulled_name` even if the expected pulled file does not exist after an ADB pull with unusual output. Add an existence check.
- Version parsing is best-effort and depends on Android `dumpsys` format.

## Recommended Tests

- Mock `manager.shell()` for `list_packages()` fallback, `get_apk_path()`, and PM action command strings.
- Mock `manager.run()` for install, install-multiple, uninstall, pull success/failure, and missing pulled output.
- Flask client tests for package mutations, file uploads, async install creation, and audit log entries.
