# ADB Manager

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Centralizes ADB discovery, bundled platform-tools install, subprocess execution, serial validation, remote-shell quoting, sentinel return-code parsing, and root-shell detection. Every other module builds on `run()`/`shell()` here rather than calling subprocess directly, so the "never build shell commands via string concatenation" rule lives in exactly one place.

## Files

- `adb/manager.py`

## Behavior

- `run()` and `run_binary()` use argv-list subprocess calls and never invoke a host shell.
- `shell()` validates serials and wraps remote commands with an `__RC__` sentinel so device-side shell exit codes are visible even when `adb shell` itself exits cleanly.
- Platform-tools download is isolated behind `download_platform_tools()`, with extraction under `config.VENDOR_DIR`.
- `install_adb()` extracts through `_safe_extract()`, which resolves every archive member against the destination directory and rejects any member (`..` segments, absolute paths) that would land outside it -- zip-slip protection, even though the download source is Google's official URL.
- On POSIX, the extracted `adb` binary has its executable bit set explicitly after extraction (`os.name != "nt"` branch).

## Known Limitations

- `shell()` assumes callers quote every dynamic remote argument themselves; high-risk operations should assert exact command strings at the route/module level rather than relying on this function to protect them.

## Testing

- `tests/test_manager.py`
- Coverage: 83%

See [`docs/module-audits/adb-manager.md`](../module-audits/adb-manager.md) for the audit history (bugs found and fixed, and any items still open).
