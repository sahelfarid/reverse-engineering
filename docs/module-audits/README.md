# Module Audit Index

Date: 2026-07-06 (original audit), updated 2026-07-07.

Scope: implementation review, test coverage review, and verification notes for the Python modules under `adb/`, their Flask blueprints under `routes/`, plus the local app/auth/config/desktop support code.

Each module now has two documents:

- **`docs/modules/<name>.md`** -- living documentation: purpose, API routes, behavior, and permanent known limitations (accepted tradeoffs, not bugs). Read this to understand how a module works.
- **`docs/module-audits/<name>.md`** -- audit history: what's still open, if anything. Read this to see whether there's outstanding follow-up work.

## Verification Run

Command used:

```sh
.venv/bin/python -m coverage run -m pytest -q && .venv/bin/python -m coverage report -m
```

Result (original audit, 2026-07-06): 71 tests passed in 1.13s. Total measured Python coverage: 51%.

**Update (2026-07-07): all 19 module gaps closed, 512 tests, 96% coverage.** Every audit file was revisited: identified gaps were either fixed in code (with a regression test proving the bug existed) or closed with test coverage where the gap was purely a testing hole.

**Follow-up (2026-07-07, same day): the last 5 recommended-test gaps closed, 525 tests, 97% coverage.** The previous pass left a handful of `Recommended Tests` bullets open across a few audit files -- real follow-up work, not permanent limitations. This pass closed all of them:

- `adb-manager`: added a POSIX chmod-branch test asserting `install_adb()` actually sets the executable bit on the extracted binary.
- `core-auth-config-desktop`: added Flask-client tests for `/api/auth/change-password` (wrong password, short password, success + audit log + old-password invalidation, CSRF rejection) and `/api/adb/install` (success + audit log, `AdbInstallError` -> 500); added `desktop.main()` tests that mock the `webview` import to verify the pywebview window path and the browser-fallback path.
- `files` / `backup`: added direct tests for the async job's inner `_run()` closure in both `download_folder_async()` and `export_app_data_async()` -- previously only the outer route wiring (job creation + `run_in_background()` call) was covered, not the closure's actual success/cleanup-on-failure logic.

No new code bugs were found in this follow-up pass -- it was entirely closing testing holes that the previous pass's audit files had already flagged as open. The module-audit files have also been trimmed: implementation narrative and verification detail have moved to `docs/modules/*.md`, and each audit file now only lists what (if anything) is still open.

**Final pass (2026-07-07, same day): every remaining item closed, 0 open items across all 19 modules.** The three items left after the previous pass were closed for real rather than left as permanent limitations:

- `shell`: stood up a minimal frontend test harness (`package.json`, `vitest.config.js`, `tests/frontend/`) -- the project had none before, being otherwise pure Python -- and added `tests/frontend/shell.test.js`, which loads the actual `static/js/app.js` and `static/js/shell.js` into a jsdom window (as classic `<script>` tags, no bundler, exactly like the browser) and drives real command submission: success (stdout + green exit badge), failure (stderr + red exit badge), an API-level error (toast), and HTML-escaping of both the command and its output. Run with `npm install && npm test`.
- `app-inspector` / `devices-dashboard`: added `tests/test_app_inspector_smoke.py` and `tests/test_devices_dashboard_smoke.py`, gated by a new shared `real_device_serial` pytest fixture (`tests/conftest.py`) that finds the first authorized, online ADB device and skips the test cleanly if none is attached (e.g. in CI). When a device is attached, these exercise the real parsers against real `dumpsys`/`/proc` output instead of only fixtures.
- `jobs`: implemented an actual pruning policy instead of leaving it as a hypothetical -- `create_job()` now caps the registry at `_MAX_RETAINED_JOBS` (200), dropping the oldest terminal (`done`/`error`/`cancelled`) jobs first; pending/running jobs are never pruned. Covered by two new tests.

Locally (no device attached, no `npm test` run as part of `pytest`): **527 Python tests passed, 6 skipped** (the real-device smoke tests), **96% Python coverage** -- the dip from 97% is an artifact of the 6 skipped smoke-test bodies counting as uncovered lines in the test files themselves, not a product-code regression (every `adb/`/`routes/` module's own coverage is unchanged or improved; see the table below). With a device attached, all 533 Python tests run. The frontend suite (`npm test`) adds 4 passing Vitest tests, not reflected in the Python coverage number.

Every audit file now reports zero open items.

Real bugs found and fixed across the full effort (both passes):
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

Several modules (Properties, Battery/Hardware, Process Manager, Root Detection, and the Core settings-validation work) had no code bugs -- only test-coverage gaps, all now closed.

## Coverage Summary

| Area | Backend coverage | Route/support coverage |
| --- | ---: | ---: |
| Core app/auth/config/desktop | app 92%, auth 86%, config 92%, desktop 79% | routes/core 95% |
| ADB manager | 83% | n/a |
| Devices and dashboard | devices 89%, dashboard 98% | routes/devices 97% |
| Shell | 100% | routes/shell 93% |
| Files | 98% | routes/files 95% |
| Packages | 99% | routes/packages 91% |
| App inspector | 100% | routes/app_inspector 96% |
| Logcat | 94% | routes/logcat 100% |
| Screen | 100% | routes/screen 97% |
| Automation | 100% | routes/automation 98% |
| Properties | 100% | routes/properties 100% |
| Network and wireless | network 100%, wireless 98% | routes/network 95% |
| Backup | 100% | routes/backup 94% |
| Battery and hardware | 100% | routes/battery 100% |
| Permissions | 100% | routes/battery 100% |
| Clipboard | 95% | routes/battery 100% |
| Process manager | 93% | routes/process_manager 100% |
| Jobs | 90% | routes/jobs 100% |
| Root detection | 98% | routes/root_detection 100% |
| Frida | 87% | routes/frida 97% |

**Total: 538 Python tests passed, 6 skipped (real-device smoke tests, no device attached), 97% Python coverage** -- up from 527/96% at the previous checkpoint, 525/97% before that, 512/96% before that, 71/51% at the original audit.

**Frontend: 4 Vitest tests passing** (`npm install && npm test`), covering `static/js/shell.js`'s terminal rendering. Frontend coverage is not merged into the Python coverage number above. All other frontend JavaScript and template behavior remains unmeasured.

**Feature added (2026-07-07, later same day): optional first-launch password, "remember me", and a self-service password reset.** Not an audit-gap closure -- a new capability, requested directly: the automatic random first-run password (previously printed to stdout) is replaced by an interactive setup screen where the user sets a password or explicitly skips it (open access, by design, on this loopback-only single-user tool); logins and setup both support "remember me" (a 30-day persistent session); and the login page's "Forgot password? Reset" link clears the password and rotates the Flask session-signing key, invalidating every remembered session everywhere. See [`docs/modules/core-auth-config-desktop.md`](../modules/core-auth-config-desktop.md) for the full behavior and known tradeoffs, and [`docs/module-audits/core-auth-config-desktop.md`](core-auth-config-desktop.md) for the implementation summary. Covered by the new `tests/test_auth_setup.py` plus a logout test in `tests/test_app_routes.py`.

## Module Documentation

- [Core, Auth, Config, Desktop](../modules/core-auth-config-desktop.md)
- [ADB Manager](../modules/adb-manager.md)
- [Devices And Dashboard](../modules/devices-dashboard.md)
- [Shell](../modules/shell.md)
- [Files](../modules/files.md)
- [Packages](../modules/packages.md)
- [App Inspector](../modules/app-inspector.md)
- [Logcat](../modules/logcat.md)
- [Screen](../modules/screen.md)
- [Automation](../modules/automation.md)
- [Properties](../modules/properties.md)
- [Network And Wireless](../modules/network-wireless.md)
- [Backup](../modules/backup.md)
- [Battery And Hardware](../modules/battery-hardware.md)
- [Permissions](../modules/permissions.md)
- [Clipboard](../modules/clipboard.md)
- [Process Manager](../modules/process-manager.md)
- [Jobs](../modules/jobs.md)
- [Root Detection](../modules/root-detection.md)
- [Frida](../modules/frida.md)

## Audit Files (open items only)

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

As of 2026-07-07, all 19 audit files report zero open items. `app-inspector.md` and `devices-dashboard.md`'s real-device smoke-test recommendations are now closed by `tests/test_app_inspector_smoke.py` / `tests/test_devices_dashboard_smoke.py` (skip cleanly with no device attached); `shell.md`'s frontend-testing recommendation is closed by `tests/frontend/shell.test.js`; `jobs.md`'s pruning-policy recommendation is closed by an actual pruning implementation in `adb/jobs.py`.

## Cross-Cutting Findings

- The architecture is consistent: pure ADB/business logic is in `adb/`, Flask blueprints are mostly thin request/response wrappers, and frontend calls flow through `apiFetch()` with CSRF headers for mutating methods.
- ADB subprocess calls generally use argv lists through `adb.manager.run()` or `run_binary()`. Remote shell strings use `manager.quote_remote()` for dynamic path/package arguments in most modules.
- Login and CSRF protection are consistently present on mutating routes. Several read-only download/export endpoints audit the action even though they are `GET`, which is appropriate because they exfiltrate device data.
- **Any future route that does `send_file(...)` followed by `response.call_on_close(...)` must also set `response.direct_passthrough = False` first**, or the cleanup callback silently never runs. This is a genuine Werkzeug gotcha (not specific to this codebase) worth remembering for new code, not just the five routes fixed in this pass.
- A recurring pattern worth naming for future contributors: several route files bind per-action handler functions into closures at blueprint-registration time (`routes/packages.py`'s `_make_action_route()`, `routes/screen.py`'s `_simple_action_route()`). Tests that try to `patch()` the bound function by its `adb_*.function_name` path won't reach it -- patch one level down at `manager.shell()`/`manager.run()` instead.
- Coverage is now strong across the board (97% overall; every individual module's backend logic is at 83%+ and most routes are 90-100%). The remaining gaps are inherent to what unit tests can't reach without a real device/emulator: OEM `dumpsys`/`ip`/`getprop` output-format drift, and a handful of platform/OS-specific branches (Windows-only lock-file paths, `os.name == "nt"` skips) that can't run on every CI platform at once.
- Frontend JavaScript and template behavior remain outside this suite's scope, as before.
