# Battery And Hardware Audit

Files: `adb/battery.py`, `routes/battery.py`, `static/js/battery.js`

Coverage: backend 15%, route 51%.

## Implementation

- Aggregates battery detail, CPU info, GPU info, sensors, and disk usage.
- Uses `devices.get_battery_info()` plus direct `dumpsys`, `/proc`, `getprop`, `SurfaceFlinger`, sensorservice, and `df` reads.
- Hardware route is read-only and login-protected.

## Verified

- No direct battery/hardware parser tests are present.

## Gaps And Risks

- Very low backend coverage for several Android/OEM-specific parsers.
- `grep` usage inside remote commands is convenient but may fail on minimal Android environments.
- Sensor and disk parsers are best-effort and may silently return empty lists.

## Recommended Tests

- Mocked parser tests for `dumpsys battery`, `/proc/cpuinfo`, GPU renderer, sensorservice variants, and `df -h`.
- Route tests for successful hardware response and ADB error mapping.
