# Shell Audit

Files: `adb/shell.py`, `routes/shell.py`, `static/js/shell.js`

Coverage: backend 100% (was 30%), route 93% (was 43%).

## Implementation

- Provides an interactive command execution endpoint over `manager.shell()`.
- Optional root mode wraps the user command with `su -c` and `manager.quote_remote()`.
- All shell execution requires login, CSRF, and audit logging with serial, `use_su`, command prefix, and return code.

## Verified

- `run_command()` is covered for empty-command short-circuit (no `manager.shell()` call), normal passthrough, `su -c` wrapping via `quote_remote()`, and timeout passthrough.
- `su_available()` is covered as a thin delegate to `manager.has_root_shell()`.
- `/shell/exec` is covered for CSRF rejection, success with audit-log detail assertions (serial, `use_su`, truncated command, returncode), `AdbNotInstalledError` -> 503, and command truncation to 500 chars in the audit entry.
- `/shell/su-available` is covered for success and `AdbError` -> 400.

## Gaps And Risks

- This module intentionally executes arbitrary user-provided commands on connected devices. That is the feature, but it remains one of the highest-risk surfaces.
- Non-root commands are passed directly as remote shell strings. This is correct for a terminal, but docs/UI should keep emphasizing local authorized use.

## Recommended Tests

- Frontend smoke tests for terminal output rendering and command failure display (out of scope for the Python test suite).
