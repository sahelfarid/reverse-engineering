# Module Audit Index

Date: 2026-07-06

Scope: implementation review, test coverage review, and verification notes for the Python modules under `adb/`, their Flask blueprints under `routes/`, plus the local app/auth/config/desktop support code.

## Verification Run

Command used:

```sh
.venv/bin/python -m coverage run -m pytest -q && .venv/bin/python -m coverage report -m
```

Result (original audit): 71 tests passed in 1.13s. Total measured Python coverage: 51%.

The system shell did not have `python`, `pytest`, or `coverage` available, so verification used a local `.venv` created from `requirements.txt` plus `coverage`.

**Update (in progress):** gaps identified below are being closed module by module -- see each audit file's "Verified"/"Gaps And Risks" sections for what has landed. Latest run: 352 tests passed, total coverage 86%, as of the network/wireless pass. Real bugs found and fixed so far: the `send_file()`/`direct_passthrough` temp-cleanup bug (fixed in `routes/files.py`, `routes/packages.py`, `routes/screen.py`; `routes/backup.py` and `routes/jobs.py` still need the same check), `pull_apk()` could return a nonexistent path, `get_permissions()`'s "requested permissions" regex bled into the next dumpsys section header, an invalid logcat query regex could crash the SSE stream, unvalidated `int()` parsing in screen/automation/network routes could turn a bad request into a 500, port validators didn't enforce the 0-65535 range, and four mutating network routes (forward/reverse remove, wireless disconnect, known-device save/delete) were missing audit logging entirely.

## Coverage Summary

| Area | Backend coverage | Route/support coverage |
| --- | ---: | ---: |
| Core app/auth/config/desktop | app 55%, auth 68%, config 92%, desktop 57% | routes/core 66% |
| ADB manager | 80% | n/a |
| Devices and dashboard | devices 89%, dashboard 98% | routes/devices 97% |
| Shell | 100% | routes/shell 93% |
| Files | 98% | routes/files 89% |
| Packages | 99% | routes/packages 91% |
| App inspector | 100% | routes/app_inspector 96% |
| Logcat | 94% | routes/logcat 100% |
| Screen | 100% | routes/screen 97% |
| Automation | 100% | routes/automation 98% |
| Properties | 100% | routes/properties 100% |
| Network and wireless | network 100%, wireless 98% | routes/network 95% |
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
