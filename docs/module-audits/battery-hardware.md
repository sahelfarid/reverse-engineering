# Battery And Hardware Audit

Files: `adb/battery.py`, `routes/battery.py`, `static/js/battery.js`

Coverage: backend 100% (was 15%), route 100% (was 51%; `routes/battery.py` is shared with the Permissions and Clipboard modules, both now also fully covered).

## Implementation

- Aggregates battery detail, CPU info, GPU info, sensors, and disk usage.
- Uses `devices.get_battery_info()` plus direct `dumpsys`, `/proc`, `getprop`, `SurfaceFlinger`, sensorservice, and `df` reads.
- Hardware route is read-only and login-protected.

## Verified

- `get_battery_detail()` (dumpsys merge + failure), `get_cpu_info()` (core counting, hardware/model extraction, failure), `get_gpu_info()` (EGL + renderer, failure), `get_sensors()` (quoted-name format, numbered fallback format, failure), `get_disk_usage()` (`df -h` parsing, failure), and `get_hardware_detail()` (composer) are all covered.
- `/api/devices/<serial>/hardware` is covered for success, `AdbNotInstalledError` -> 503, `AdbError` -> 400, and login-required 401.

## Gaps And Risks

- `grep` usage inside remote commands (`get_gpu_info()`'s `dumpsys SurfaceFlinger | grep -i GLES`) is convenient but may fail on minimal Android environments without `grep`; unchanged from the original audit, and not something a unit test against mocked output can validate.
- Sensor and disk parsers are best-effort and may silently return empty lists on unexpected OEM formats -- documented behavior, not a bug.

## Recommended Tests

- None outstanding for this module's Python surface. `routes/battery.py`'s permission and clipboard endpoints are tracked under the Permissions and Clipboard audits respectively, since that's where their backend logic lives.
