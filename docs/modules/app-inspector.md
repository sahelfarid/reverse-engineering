# App Inspector

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Gathers requested/granted/denied permissions, CPU ABI values, exported-ish component references from global `dumpsys package`, and app data/database/shared-preference visibility for a single package.

## Files

- `adb/app_inspector.py`
- `routes/app_inspector.py`
- `static/js/inspector.js`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices/<serial>/packages/<package>/inspect` | Full app detail composite (permissions, components, data dirs). |
| POST | `/api/devices/<serial>/packages/<package>/restart` | Force-stop then relaunch the package. CSRF-protected, audit-logged. |

## Behavior

- Package names are validated through `adb.packages.validate_package()` before use.
- Data-directory access attempts `run-as` first and root fallback (`su -c`) second.
- The restart route delegates to package restart and is CSRF-protected and audit-logged.

## Known Limitations

- `get_components()` scans global `dumpsys package` output and may still include false positives or miss components on OEM-specific formats; documented best-effort limitation.
- Root fallback in `get_data_dirs()` builds `f"su -c '{cmd_suffix}'"` without wrapping the whole command in `manager.quote_remote()`, but `cmd_suffix` is built only from an already-validated package name and static strings, so there is no user-controlled injection surface.

## Testing

- `tests/test_app_inspector.py`
- `tests/test_app_inspector_routes.py`
- `tests/test_app_inspector_smoke.py` -- real-device smoke test (via the `real_device_serial` fixture) that runs `get_permissions()`/`get_components()`/`get_app_detail()` against a real, attached device's `android` system package, to catch OEM `dumpsys` format drift the mocked fixtures can't. Skips automatically when no authorized device is attached (e.g. in CI).
- Coverage: 100% backend, 96% route

See [`docs/module-audits/app-inspector.md`](../module-audits/app-inspector.md) for the audit history (bugs found and fixed, and any items still open).
