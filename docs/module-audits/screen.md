# Screen Audit

Files: `adb/screen.py`, `routes/screen.py`, `static/js/screen.js`

Coverage: backend 24%, route 49%.

## Implementation

- Supports screenshot, screenrecord start/stop/status/pull, rotation lock/set, wake, sleep, and brightness.
- Screenshots use binary `exec-out screencap -p`.
- Recording state is process-local and keyed by serial.
- Brightness is clamped to 0..255; rotation accepts only 0, 90, 180, and 270.
- Mutating routes require login, CSRF, and audit logging.

## Verified

- No direct backend tests beyond shared manager behavior.

## Gaps And Risks

- Active recording state is lost on server restart and does not verify that the remote PID is still alive.
- `stop_recording()` sends `kill -INT` to a stored PID without revalidating it belongs to `screenrecord`.
- Route parsing uses `int()` directly; malformed JSON values can raise 500s instead of returning 400s.

## Recommended Tests

- Mocked tests for screenshot binary success/failure, recording start duplicate handling, stop without active recording, rotation validation, and brightness clamping.
- Route tests for malformed `degrees`, `level`, and `time_limit_sec` values.
- Temp cleanup tests for record pull.
