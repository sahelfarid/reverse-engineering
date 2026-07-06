# Devices And Dashboard Audit

Files: `adb/devices.py`, `adb/dashboard.py`, `routes/devices.py`, `static/js/devices.js`, `static/js/dashboard.js`

Coverage: devices 35%, dashboard 15%, routes/devices 54%.

## Implementation

- `devices.py` parses `adb devices -l`, includes fastboot discovery, and gathers basic device properties, battery, storage, and root availability.
- `dashboard.py` composes lightweight status cards for CPU/memory, app counts, screen state, foreground app, Wi-Fi, and root availability.
- `routes/devices.py` exposes device list, device detail, and dashboard overview behind login.

## Verified

- `adb devices -l` parser is covered for authorized USB devices, unauthorized devices, wireless devices, headers, and blank lines.
- Route auth gating is indirectly covered by app route tests.

## Gaps And Risks

- Fastboot detection uses direct `subprocess.run()` because fastboot is not ADB. It is not covered.
- `get_basic_properties()` uses one shell call per property; this is simple but slower than a batched read.
- Dashboard parsing of `/proc`, `dumpsys`, and `grep` output is not covered and may vary by Android version/OEM.

## Recommended Tests

- Mock `manager.run()` for `list_devices()` and mock `subprocess.run()` for `list_fastboot_devices()`.
- Mock `manager.shell()` for battery/storage/property/dashboard parsers, including missing or malformed output.
- Flask client tests for `/api/devices`, `/api/devices/<serial>`, and `/api/devices/<serial>/overview` error mapping.
