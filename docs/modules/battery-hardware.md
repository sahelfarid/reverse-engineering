# Battery And Hardware

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Aggregates battery detail, CPU info, GPU info, sensors, and disk usage into one hardware snapshot.

## Files

- `adb/battery.py`
- `routes/battery.py`
- `static/js/battery.js`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices/<serial>/hardware` | Composite hardware detail (battery, CPU, GPU, sensors, disk). |

## Behavior

- Uses `devices.get_battery_info()` plus direct `dumpsys`, `/proc`, `getprop`, `SurfaceFlinger`, sensorservice, and `df` reads.
- The hardware route is read-only and login-protected.

## Known Limitations

- `get_gpu_info()`'s `dumpsys SurfaceFlinger | grep -i GLES` is convenient but may fail on minimal Android environments without `grep`.
- Sensor and disk parsers are best-effort and may silently return empty lists on unexpected OEM formats.

## Testing

- `tests/test_battery.py`
- `tests/test_battery_routes.py`
- Coverage: 100% backend, 100% route

See [`docs/module-audits/battery-hardware.md`](../module-audits/battery-hardware.md) for the audit history (bugs found and fixed, and any items still open).
