# Process Manager Audit

Files: `adb/process_manager.py`, `routes/process_manager.py`, `static/js/processes.js`

Coverage: backend 93% (was 64%), route 100% (was 50%).

## Implementation

- Lists processes using `ps -A -o PID,PPID,USER,RSS,NAME`, falls back to `ps -A`, and parses column indexes from the header.
- Reuses dashboard foreground-app implementation.
- Kill operation sanitizes signal names, tries normal kill first, then root kill if available.
- Kill route requires login, CSRF, and audit logging.

## Verified

- Process parser is covered for named columns, empty/failing output, the `ps -A` fallback format, short/truncated rows (marks `parseable: False` and skips the row), and PID-based sort ordering.
- `kill_process()` is covered for success, signal-name sanitization (strips shell metacharacters, defaults to `TERM` when nothing alphanumeric remains), root fallback success, root fallback failure, permission-denied without root, and string-PID input.
- Every route is covered: `processes`, `foreground-app`, and `processes/<pid>/kill` (success + audit log, default signal, `AdbError` mapping, CSRF rejection, login-required 401).

**Investigated and found not to be an issue:** the "malformed PID can raise" concern from the original audit doesn't actually manifest -- the only route calling `adb_process_manager.kill_process()` declares its path as `/processes/<int:pid>/kill`, so Flask's own URL converter rejects non-numeric PIDs with a 404 *before* the view function (and therefore `kill_process()`'s `int(pid)`) ever runs. Confirmed with `test_kill_process_rejects_non_numeric_pid_at_route_level`. `kill_process()`'s `int(pid)` coercion is retained since it's a harmless no-op for the already-int value Flask passes in, and it keeps the function safe to call directly (e.g. from a script or future route) with a numeric string.

## Gaps And Risks

- The process parser still skips rows with fewer columns than the header, which is safe but can hide OEM format drift; this is inherent to defensive parsing of `ps` output and not something more unit tests can fully close.

## Recommended Tests

- None outstanding for this module's Python surface.
