# Devices And Dashboard

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Device discovery and a lightweight per-device status overview used by the dashboard UI.

## Files

- `adb/devices.py`
- `adb/dashboard.py`
- `routes/devices.py`
- `static/js/devices.js`
- `static/js/dashboard.js`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices` | List connected ADB (and fastboot) devices. |
| GET | `/api/devices/<serial>` | Basic device properties, battery, storage, root availability. |
| GET | `/api/devices/<serial>/overview` | Dashboard cards: CPU/mem, app count, screen, foreground app, Wi-Fi, root. |

## Behavior

- `devices.py` parses `adb devices -l`, includes fastboot discovery, and gathers basic device properties, battery, storage, and root availability.
- `dashboard.py` composes lightweight status cards for CPU/memory, app counts, screen state, foreground app, Wi-Fi, and root availability.
- `routes/devices.py` exposes device list, device detail, and dashboard overview, all behind login.

## Known Limitations

- `get_basic_properties()` uses one shell call per property; simple but slower than a batched read. Left as-is: a correctness gap, not a bug, and batching would touch the sentinel-parsing contract in `manager.shell()`.
- Dashboard/device parsers are unit-tested against representative and malformed `dumpsys`/`/proc` output, but real OEM output can still vary.

## Testing

- `tests/test_devices.py`
- `tests/test_dashboard.py`
- `tests/test_devices_routes.py`
- `tests/test_devices_dashboard_smoke.py` -- real-device smoke test (via the `real_device_serial` fixture) that runs `list_devices()`, `get_device_detail()`, and `dashboard.get_overview()` against a real, attached device, to catch OEM `dumpsys`/`/proc` format drift the mocked fixtures can't. Skips automatically when no authorized device is attached (e.g. in CI).
- Coverage: devices 89%, dashboard 98%, routes/devices 97%

See [`docs/module-audits/devices-dashboard.md`](../module-audits/devices-dashboard.md) for the audit history (bugs found and fixed, and any items still open).
