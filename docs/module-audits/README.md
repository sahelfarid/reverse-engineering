# Module Audit Index

Date: 2026-07-06

Scope: implementation review, test coverage review, and verification notes for the Python modules under `adb/`, their Flask blueprints under `routes/`, plus the local app/auth/config/desktop support code.

## Verification Run

Command used:

```sh
.venv/bin/python -m coverage run -m pytest -q && .venv/bin/python -m coverage report -m
```

Result: 71 tests passed in 1.13s. Total measured Python coverage: 51%.

The system shell did not have `python`, `pytest`, or `coverage` available, so verification used a local `.venv` created from `requirements.txt` plus `coverage`.

## Coverage Summary

| Area | Backend coverage | Route/support coverage |
| --- | ---: | ---: |
| Core app/auth/config/desktop | app 55%, auth 62%, config 83%, desktop 44% | routes/core 55% |
| ADB manager | 50% | n/a |
| Devices and dashboard | devices 35%, dashboard 15% | routes/devices 54% |
| Shell | 30% | routes/shell 43% |
| Files | 36% | routes/files 24% |
| Packages | 39% | routes/packages 35% |
| App inspector | 13% | routes/app_inspector 46% |
| Logcat | 32% | routes/logcat 39% |
| Screen | 24% | routes/screen 49% |
| Automation | 39% | routes/automation 48% |
| Properties | 92% | routes/properties 53% |
| Network and wireless | network 21%, wireless 27% | routes/network 53% |
| Backup | 19% | routes/backup 30% |
| Battery and hardware | 15% | routes/battery 51% |
| Permissions | 35% | routes/battery 51% |
| Clipboard | 62% | routes/battery 51% |
| Process manager | 64% | routes/process_manager 50% |
| Jobs | 61% | routes/jobs 50% |
| Root detection | 82% | routes/root_detection 53% |
| Frida | 45% | routes/frida 43% |

Frontend JavaScript and template behavior are not measured by the current test suite.

## Audit Files

- [Core, Auth, Config, Desktop](core-auth-config-desktop.md)
- [ADB Manager](adb-manager.md)
- [Devices And Dashboard](devices-dashboard.md)
- [Shell](shell.md)
- [Files](files.md)
- [Packages](packages.md)
- [App Inspector](app-inspector.md)
- [Logcat](logcat.md)
- [Screen](screen.md)
- [Automation](automation.md)
- [Properties](properties.md)
- [Network And Wireless](network-wireless.md)
- [Backup](backup.md)
- [Battery And Hardware](battery-hardware.md)
- [Permissions](permissions.md)
- [Clipboard](clipboard.md)
- [Process Manager](process-manager.md)
- [Jobs](jobs.md)
- [Root Detection](root-detection.md)
- [Frida](frida.md)

## Cross-Cutting Findings

- The architecture is consistent: pure ADB/business logic is in `adb/`, Flask blueprints are mostly thin request/response wrappers, and frontend calls flow through `apiFetch()` with CSRF headers for mutating methods.
- ADB subprocess calls generally use argv lists through `adb.manager.run()` or `run_binary()`. Remote shell strings use `manager.quote_remote()` for dynamic path/package arguments in most modules.
- Login and CSRF protection are consistently present on mutating routes. Several read-only download/export endpoints audit the action even though they are `GET`, which is appropriate because they exfiltrate device data.
- Coverage is strongest for parsing, validation, root-detection summaries, jobs lifecycle, and portable path helpers.
- Coverage is weakest for device-dependent workflows, route error paths, file transfer cleanup behavior, and frontend behavior. These should be tested with mocked `manager.shell()`, `manager.run()`, Flask clients, and browser-level smoke tests rather than real devices for unit coverage.
