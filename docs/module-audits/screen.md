# Screen Audit

Files: `adb/screen.py`, `routes/screen.py`, `static/js/screen.js`

Coverage: backend 100% (was 24%), route 97% (was 49%).

## Implementation

- Supports screenshot, screenrecord start/stop/status/pull, rotation lock/set, wake, sleep, and brightness.
- Screenshots use binary `exec-out screencap -p`.
- Recording state is process-local and keyed by serial.
- Brightness is clamped to 0..255; rotation accepts only 0, 90, 180, and 270.
- Mutating routes require login, CSRF, and audit logging.

## Verified

- `take_screenshot()`, `start_recording()` (success, already-active, non-digit-pid failure), `stop_recording()` (success + kill command construction, no-active-recording), `recording_status()`, `set_rotation()` (valid + invalid degrees), `unlock_auto_rotation()`/`wake_device()`/`sleep_device()`, and `set_brightness()` (clamping at both ends) are all covered with a mocked `manager.shell()`/`manager.run_binary()`.
- Every route is covered: `screenshot` (success + `AdbError` mapping), `record/start` (success, audit log, malformed `time_limit_sec` -> 400), `record/stop`, `record/status`, `record/pull` (success with temp cleanup, `AdbError` mapping with cleanup still happening), `rotate`/`brightness` (success + malformed-input 400), `auto-rotate`/`wake`/`sleep` (success, CSRF rejection, `AdbError` mapping).

**Two real bugs found and fixed while writing these tests:**
1. `record_start()` and `_simple_action_route()` (backing `rotate` and `brightness`) called `int(...)` directly on user-supplied JSON values. A non-numeric `time_limit_sec`, `degrees`, or `level` raised an uncaught `ValueError`, producing an unhandled-exception 500 instead of a clean 400. Fixed by wrapping each `int()` call in `try/except (TypeError, ValueError)` and returning `{"ok": False, "error": "invalid_time_limit_sec"}` / `{"ok": False, "error": "invalid_arguments"}` with a 400.
2. `record_pull()` had the same `send_file()`/`direct_passthrough` cleanup bug as `routes/files.py` and `routes/packages.py` -- `call_on_close()` never fired. Fixed the same way: `response.direct_passthrough = False` before registering the callback.

## Gaps And Risks

- Active recording state is still lost on server restart and does not verify that the remote PID is still alive (unchanged; in-memory-only registry is a documented, accepted tradeoff for a local single-user tool).
- `stop_recording()` still sends `kill -INT` to a stored PID without revalidating it belongs to `screenrecord`. Left as-is rather than adding an unverified `ps -p <pid>` check: Android's `ps -o` column support varies across toybox/busybox versions, and the PID-reuse window in practice (a single local device, seconds between record-stop calls) is narrow. Documented here as an accepted risk rather than silently dropped.

## Recommended Tests

- None outstanding for this module's Python surface.
