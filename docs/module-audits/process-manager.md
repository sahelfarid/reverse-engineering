# Process Manager Audit

Files: `adb/process_manager.py`, `routes/process_manager.py`, `static/js/processes.js`

Coverage: backend 64%, route 50%.

## Implementation

- Lists processes using `ps -A -o PID,PPID,USER,RSS,NAME`, falls back to `ps -A`, and parses column indexes from the header.
- Reuses dashboard foreground-app implementation.
- Kill operation sanitizes signal names, tries normal kill first, then root kill if available.
- Kill route requires login, CSRF, and audit logging.

## Verified

- Process parser is covered for named columns and empty/failing output.

## Gaps And Risks

- Kill behavior and root fallback are not tested.
- PID parsing in route path uses Flask path conversion as string then `int()` in backend; malformed PID can raise if route passes non-numeric values.
- The process parser skips rows with fewer columns, which is safe but can hide OEM format drift.

## Recommended Tests

- Unit tests for kill success, root fallback success, permission denied, invalid signals, and invalid PIDs.
- Parser fixture tests for fallback `ps -A` formats.
- Route tests for CSRF, audit details, and ADB error mapping.
