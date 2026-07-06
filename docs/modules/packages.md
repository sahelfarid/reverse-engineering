# Packages

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Package management: listing, install/uninstall, enable/disable, clear-data, force-stop, launch/restart, and APK extraction.

## Files

- `adb/packages.py`
- `routes/packages.py`
- `static/js/packages.js`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices/<serial>/packages` | List installed packages. |
| GET | `/api/devices/<serial>/packages/<package>/size` | APK path + size. |
| POST | `/api/devices/<serial>/packages/install` | Install one or more APKs (sync). |
| POST | `/api/devices/<serial>/packages/install/async` | Same, as a background job. |
| POST | `/api/devices/<serial>/packages/<package>/uninstall` | Uninstall (optionally keeping data with `-k`). |
| POST | `/api/devices/<serial>/packages/<package>/{disable,enable,clear-data,force-stop,launch}` | PM actions, bound via `_make_action_route()`. |
| GET | `/api/devices/<serial>/packages/<package>/pull` | Pull the package's APK. |

## Behavior

- Supports package listing, APK path and size lookup, install/install-multiple, uninstall, disable, enable, clear data, force-stop, launch, restart, and APK pull.
- Package names are validated with a strict Java-style package regex before shell use.
- Installs use host argv-list ADB calls. PM actions quote package names before device shell commands.
- Routes require login and CSRF for mutations. APK pull is read-only in HTTP method terms but audit-logged because it exports device data.
- `pull_apk()` raises `AdbError` rather than returning a dangling path if `adb pull` reports success but the file didn't actually land where expected.
- The same `send_file()` + `call_on_close()` temp-dir cleanup fix used in Files/Backup/Screen/Jobs is applied to the APK-pull route.

## Known Limitations

- Version parsing is best-effort and depends on Android `dumpsys` format.
- `_make_action_route()` binds each PM action's backend function into a closure at blueprint-registration (import) time. Tests must patch at `manager.shell()` rather than at the `adb_packages.<fn>` name, or the patch silently misses the bound closure.

## Testing

- `tests/test_packages.py`
- `tests/test_packages_routes.py`
- Coverage: 99% backend, 91% route

See [`docs/module-audits/packages.md`](../module-audits/packages.md) for the audit history (bugs found and fixed, and any items still open).
