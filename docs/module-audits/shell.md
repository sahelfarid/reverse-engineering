# Shell Audit

Files: `adb/shell.py`, `routes/shell.py`, `static/js/shell.js`

Coverage: backend 30%, route 43%.

## Implementation

- Provides an interactive command execution endpoint over `manager.shell()`.
- Optional root mode wraps the user command with `su -c` and `manager.quote_remote()`.
- All shell execution requires login, CSRF, and audit logging with serial, `use_su`, command prefix, and return code.

## Verified

- Core remote-command execution behavior is partially covered through `adb.manager.shell()` tests.
- Auth and CSRF behavior are covered generically by app route tests.

## Gaps And Risks

- This module intentionally executes arbitrary user-provided commands on connected devices. That is the feature, but it remains one of the highest-risk surfaces.
- Non-root commands are passed directly as remote shell strings. This is correct for a terminal, but docs/UI should keep emphasizing local authorized use.
- No tests cover route JSON handling, audit log details, empty command behavior, or root wrapping.

## Recommended Tests

- Unit tests for `run_command()` empty command, normal command, root command wrapping, and ADB errors.
- Flask client tests asserting CSRF protection and audit logging for `/shell/exec`.
- Frontend smoke tests for terminal output rendering and command failure display.
