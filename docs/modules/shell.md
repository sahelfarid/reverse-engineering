# Shell

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

An interactive command-execution endpoint -- effectively a device terminal.

## Files

- `adb/shell.py`
- `routes/shell.py`
- `static/js/shell.js`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices/<serial>/shell/su-available` | Whether a root shell is available. |
| POST | `/api/devices/<serial>/shell/exec` | Run a command, optionally as root. |

## Behavior

- Provides an interactive command execution endpoint over `manager.shell()`.
- Optional root mode wraps the user command with `su -c` and `manager.quote_remote()`.
- All shell execution requires login, CSRF, and audit logging with serial, `use_su`, command prefix (truncated to 500 chars), and return code.

## Known Limitations

- This module intentionally executes arbitrary user-provided commands on connected devices. That's the feature, but it remains one of the highest-risk surfaces in the app -- docs/UI should keep emphasizing local authorized use.
- Non-root commands are passed directly as remote shell strings, which is correct for a terminal but worth keeping in mind for anyone extending this route.

## Testing

- `tests/test_shell.py`
- `tests/test_shell_routes.py`
- `tests/frontend/shell.test.js` -- frontend smoke tests for `static/js/shell.js` (terminal output rendering, stdout/stderr/exit-code display, error toasts, HTML escaping). Run with `npm install && npm test` (Vitest + jsdom; no bundler -- the real `static/js/*.js` files are loaded as classic scripts, same as the browser).
- Coverage: 100% backend, 93% route

See [`docs/module-audits/shell.md`](../module-audits/shell.md) for the audit history (bugs found and fixed, and any items still open).
