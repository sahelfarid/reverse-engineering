# Logcat Audit

Files: `adb/logcat.py`, `routes/logcat.py`, `static/js/logcat.js`

Coverage: backend 32%, route 39%.

## Implementation

- Streams `adb logcat -v threadtime` via SSE with optional server-side tag, pid, level, and regex filters.
- Package-to-pid resolution uses `pidof`.
- Clear route requires login, CSRF, and audit logging.
- Subprocess is terminated in a `finally` block when the stream closes.

## Verified

- Threadtime parser is covered for normal lines, error-level lines, and garbled fallback lines.

## Gaps And Risks

- Streaming behavior, process cleanup, regex filtering, and route SSE framing are not tested.
- Query regex is compiled directly from user input. Invalid regex patterns can raise and break the stream; consider catching `re.error` and returning a structured error.
- `resolve_pid()` is untested.

## Recommended Tests

- Unit tests for level ordering, tag/pid/query filtering, invalid regex handling, and process cleanup.
- Flask streaming tests for SSE `data:` entries and error events.
- Mocked clear-logcat route tests with CSRF and audit assertions.
