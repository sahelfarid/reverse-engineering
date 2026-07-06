# Root Detection Audit

Files: `adb/root_detection.py`, `routes/root_detection.py`

Coverage: backend 82%, route 53%.

## Implementation

- Checks su paths, working root shell, Magisk package, Magisk artifacts, busybox, build tags, debug/secure flags, verified boot state, bootloader lock, and SELinux mode.
- Batches path checks and build property reads to reduce device round trips.
- Summary returns a verdict plus matched indicator evidence, not just a boolean.
- Route is read-only, login-protected, and intentionally does not require CSRF.

## Verified

- Summary verdicts are covered for all-clear, working root, su-only, Magisk-only, and weak-signal-only combinations.
- Build integrity parsing is covered including partial output.
- su path parsing and Magisk installed detection are covered.

## Gaps And Risks

- `get_integrity_report()` orchestration is not directly tested.
- Busybox detection is not covered.
- Host-side detection remains best-effort and can be defeated by root hiding; the module documents this limitation clearly.

## Recommended Tests

- Orchestration tests with all helper calls mocked, including `manager.validate_serial()`.
- Busybox success/failure tests.
- Flask client tests for route success, ADB not installed, generic ADB errors, and response shape.
