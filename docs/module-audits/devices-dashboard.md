# Devices And Dashboard Audit

Files: `adb/devices.py`, `adb/dashboard.py`, `routes/devices.py`, `static/js/devices.js`, `static/js/dashboard.js`

Coverage: devices 89% (was 35%), dashboard 98% (was 15%), routes/devices 97% (was 54%).

## Implementation

- `devices.py` parses `adb devices -l`, includes fastboot discovery, and gathers basic device properties, battery, storage, and root availability.
- `dashboard.py` composes lightweight status cards for CPU/memory, app counts, screen state, foreground app, Wi-Fi, and root availability.
- `routes/devices.py` exposes device list, device detail, and dashboard overview behind login.

## Verified

- `adb devices -l` parser is covered for authorized USB devices, unauthorized devices, wireless devices, headers, and blank lines.
- `list_devices()` is covered with a mocked `manager.run()`; `list_fastboot_devices()` is covered for no-fastboot-found, a parsed device line, and a `subprocess.TimeoutExpired` mapping to an empty list.
- `get_basic_properties()`, `get_battery_info()`, `get_storage_info()`, and `get_device_detail()` are covered for success and failure/empty-output paths with a mocked `manager.shell()`.
- Every `adb/dashboard.py` composer (`get_cpu_mem`, `get_running_apps_count`, `get_screen_status`, `get_foreground_app`, `get_wifi_status`, `get_overview`) is covered for success, failure, and no-match parsing branches.
- `routes/devices.py` is covered end-to-end (mocked backend calls) for all three endpoints' success paths, `AdbNotInstalledError` -> 503, `AdbError` -> 400, and login-required 401s. New tests live in `tests/test_devices_routes.py`, which also introduces a shared `auth_client` fixture in `tests/conftest.py` for future route tests.

## Gaps And Risks

- `get_basic_properties()` uses one shell call per property; this is simple but slower than a batched read. Left as-is: correctness gap, not a bug, and batching would touch the sentinel-parsing contract in `manager.shell()`.
- Dashboard/device parsers are now unit-tested against representative and malformed `dumpsys`/`/proc` output, but real OEM output can still vary; this is a best-effort limitation the module already documents implicitly through its regex-based parsing.

## Recommended Tests

- Real-device or emulator smoke tests to catch OEM-specific `dumpsys`/`/proc` format drift that mocked unit tests can't anticipate.
