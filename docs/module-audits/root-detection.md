# Root Detection Audit

Files: `adb/root_detection.py`, `routes/root_detection.py`

Coverage: backend 98% (was 82%), route 100% (was 53%).

## Implementation

- Checks su paths, working root shell, Magisk package, Magisk artifacts, busybox, build tags, debug/secure flags, verified boot state, bootloader lock, and SELinux mode.
- Batches path checks and build property reads to reduce device round trips.
- Summary returns a verdict plus matched indicator evidence, not just a boolean.
- Route is read-only, login-protected, and intentionally does not require CSRF.

## Verified

- Summary verdicts are covered for all-clear, working root, su-only, Magisk-only, weak-signal-only, and busybox-only combinations.
- Build integrity parsing is covered including partial output.
- su path parsing and Magisk installed/not-installed detection are covered.
- `check_busybox()` is covered for found and not-found (both nonzero exit and empty-output-with-rc-0) cases.
- `get_integrity_report()` orchestration is covered: verifies every helper (`check_su_paths`, `check_magisk`, `check_busybox`, `check_build_integrity`, `manager.has_root_shell`) is called exactly once with the serial, the disclaimer text is present, and `manager.validate_serial()` is checked first (an `AdbError` there propagates before any device calls).
- Route is covered for success, `AdbNotInstalledError` -> 503, `AdbError` -> 400, and login-required 401.

## Gaps And Risks

- Host-side detection remains best-effort and can be defeated by root hiding (Magisk DenyList, custom kernels); the module documents this limitation clearly in its own docstring and disclaimer, and no amount of unit testing changes that inherent limitation.

## Recommended Tests

- None outstanding for this module's Python surface.
