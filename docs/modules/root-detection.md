# Root Detection

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Best-effort host-side check for whether a connected device appears to be rooted, with a documented disclaimer about its limits.

## Files

- `adb/root_detection.py`
- `routes/root_detection.py`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices/<serial>/integrity` | Root/integrity report: verdict plus matched indicator evidence. |

## Behavior

- Checks su paths, working root shell, Magisk package, Magisk artifacts, busybox, build tags, debug/secure flags, verified boot state, bootloader lock, and SELinux mode.
- Batches path checks and build property reads to reduce device round trips.
- The summary returns a verdict plus matched indicator evidence, not just a boolean.
- The route is read-only, login-protected, and intentionally does not require CSRF.

## Known Limitations

- Host-side detection remains best-effort and can be defeated by root hiding (Magisk DenyList, custom kernels); the module documents this limitation directly in its own docstring and disclaimer.

## Testing

- `tests/test_root_detection.py`
- `tests/test_root_detection_routes.py`
- Coverage: 98% backend, 100% route

See [`docs/module-audits/root-detection.md`](../module-audits/root-detection.md) for the audit history (bugs found and fixed, and any items still open).
