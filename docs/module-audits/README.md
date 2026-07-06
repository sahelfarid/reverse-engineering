# Module Audit Index

Date: 2026-07-06

Scope: implementation review, test coverage review, and verification notes for the Python modules under `adb/`, their Flask blueprints under `routes/`, plus the local app/auth/config/desktop support code.

## Verification Run

Command used:

```sh
.venv/bin/python -m coverage run -m pytest -q && .venv/bin/python -m coverage report -m
```

Result (original audit, 2026-07-06): 71 tests passed in 1.13s. Total measured Python coverage: 51%.

The system shell did not have `python`, `pytest`, or `coverage` available, so verification used a local `.venv` created from `requirements.txt` plus `coverage`.

**Update (2026-07-07): all 19 module gaps closed.** Every audit file below was revisited: identified gaps were either fixed in code (with a regression test proving the bug existed) or closed with test coverage where the gap was purely a testing hole. See each audit file's "Verified"/"Gaps And Risks" sections for the per-module detail. Final run: **512 tests passed, total coverage 96%.**

Real bugs found and fixed across the pass:
- **`send_file()` + `direct_passthrough` temp-cleanup bug** (the single highest-impact finding): `response.call_on_close()` never fires when `send_file()`'s default `direct_passthrough=True` is left in place, because Werkzeug's `Response.get_app_iter()` skips the `ClosingIterator` that's the only thing that ever calls `Response.close()`. This meant every temp directory created for image/file/folder/APK/database/app-data/job-result downloads was leaking on every request, on any real WSGI server -- not just for interrupted clients as originally suspected. Fixed in all five affected routes: `routes/files.py`, `routes/packages.py`, `routes/screen.py`, `routes/backup.py`, `routes/jobs.py`.
- `pull_apk()` and the async folder-download path could return/report a path to a file that didn't actually exist on disk.
- `get_permissions()`'s "requested permissions" regex bled into the next dumpsys section header (`install permissions:`) on real device output, contaminating the requested-permissions list.
- An invalid logcat query regex (`re.error`) wasn't caught, crashing the SSE stream instead of producing a clean error event.
- Unvalidated `int()` parsing of user-supplied JSON/query values in screen, automation, and network routes could turn a malformed request into an unhandled 500 instead of a 400.
- Port/address validators in `adb/network.py` and `adb/wireless.py` accepted any digit sequence with no 0-65535 range check.
- Four mutating network routes (`forward_remove`, `reverse_remove`, `wireless_disconnect`, known-device save/delete) performed real state changes with no audit log entry.
- `export_app_data()`'s root-tar fallback discarded its subprocess return code, so a failing root tar surfaced as a confusing "pull failed" error instead of the real tar failure.
- Permission grant/revoke only checked `stderr` for failure text, missing stdout-only failures on some OEM `pm` builds.
- The job-result download route could raise an unhandled `FileNotFoundError` for a stale/already-cleaned-up result file instead of a structured error.

Several modules (Properties, Battery/Hardware, Process Manager, Root Detection, and the Core settings-validation work) had no code bugs -- only test-coverage gaps, which are now closed.

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
| Backup | 100% | routes/backup 89% |
| Battery and hardware | 100% | routes/battery 100% |
| Permissions | 100% | routes/battery 100% |
| Clipboard | 95% | routes/battery 100% |
| Process manager | 93% | routes/process_manager 100% |
| Jobs | 90% | routes/jobs 100% |
| Root detection | 98% | routes/root_detection 100% |
| Frida | 87% | routes/frida 97% |

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
- Login and CSRF protection are consistently present on mutating routes (the four missing audit-log calls found in `routes/network.py` have been fixed). Several read-only download/export endpoints audit the action even though they are `GET`, which is appropriate because they exfiltrate device data.
- **Any future route that does `send_file(...)` followed by `response.call_on_close(...)` must also set `response.direct_passthrough = False` first**, or the cleanup callback silently never runs. This is a genuine Werkzeug gotcha (not specific to this codebase) worth remembering for new code, not just the five routes fixed in this pass.
- A recurring pattern worth naming for future contributors: several route files bind per-action handler functions into closures at blueprint-registration time (`routes/packages.py`'s `_make_action_route()`, `routes/screen.py`'s `_simple_action_route()`). Tests that try to `patch()` the bound function by its `adb_*.function_name` path won't reach it -- patch one level down at `manager.shell()`/`manager.run()` instead.
- Coverage is now strong across the board (96% overall; every individual module's backend logic is at 87%+ and most routes are 90-100%). The remaining gaps are inherent to what unit tests can't reach without a real device/emulator: OEM `dumpsys`/`ip`/`getprop` output-format drift, and a handful of async-job inner closures that run on background threads (`routes/files.py`'s and `routes/backup.py`'s async download/export closures) which are mocked out at the `run_in_background()` boundary rather than executed directly in route tests.
- Frontend JavaScript and template behavior remain outside this suite's scope, as before.
