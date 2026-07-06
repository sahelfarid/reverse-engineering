# Logcat Audit

Files: `adb/logcat.py`, `routes/logcat.py`, `static/js/logcat.js`

Coverage: backend 94% (was 32%), route 100% (was 39%).

## Implementation

- Streams `adb logcat -v threadtime` via SSE with optional server-side tag, pid, level, and regex filters.
- Package-to-pid resolution uses `pidof`.
- Clear route requires login, CSRF, and audit logging.
- Subprocess is terminated in a `finally` block when the stream closes.

## Verified

- Threadtime parser is covered for normal lines, error-level lines, and garbled fallback lines.
- `resolve_pid()` is covered for success, shell failure, and empty-output cases.
- `clear_logcat()` is covered for success and failure.
- `stream_logcat()` is covered for normal entry yielding, tag/pid/level filtering, query-regex filtering, `AdbNotInstalledError` when adb is missing, and process `terminate()` on both stream exhaustion and early consumer disconnect (`generator.close()`).
- `/logcat/stream` is covered for SSE `data:` framing, the `event: error` path, `package` -> `resolve_pid()` -> `pid` wiring, and login-required 401. `/logcat/clear` is covered for CSRF rejection, success + audit log, and `AdbNotInstalledError` -> 503.

**A real bug found and fixed while writing these tests:** `stream_logcat()` compiled the caller-supplied `query` into a regex with plain `re.compile(query, re.IGNORECASE)`. An invalid pattern (e.g. an unbalanced `(`) raised `re.error`, which was not an `AdbError` -- so the route's `except adb_manager.AdbError` in `routes/logcat.py` never caught it, and the exception would propagate out of the SSE generator mid-stream instead of producing a clean `event: error` response. Fixed by catching `re.error` in `stream_logcat()` and re-raising as `manager.AdbError(f"invalid regex query: {exc}")`, which the existing route handler already knows how to turn into a proper SSE error event. Covered by `test_stream_logcat_raises_adb_error_on_invalid_regex`.

## Gaps And Risks

- None outstanding for this module's Python surface. The two remaining uncovered lines in `adb/logcat.py` are the `TimeoutExpired` -> `process.kill()` fallback in the `finally` block, which needs a real hung subprocess to exercise meaningfully rather than a mock.

## Recommended Tests

- None outstanding; frontend SSE consumption (`static/js/logcat.js`) remains out of scope for the Python suite.
