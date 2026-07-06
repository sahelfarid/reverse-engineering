# Root Detection Implementation Notes

## Status

Implemented.

The integrity workflow reports host-side, best-effort root and device-integrity
signals with raw evidence, then summarizes them without pretending to be a
replacement for Play Integrity or other on-device attestations.

## Implemented Surface

- Batched checks for common `su` paths.
- Shared `manager.has_root_shell()` check for a working root shell.
- Magisk package and filesystem-artifact checks.
- Busybox presence as a weak/corroborating signal.
- Build-tag, debuggable, secure, verified-boot, bootloader-lock, and SELinux
  indicators.
- A summary verdict of `rooted`, `likely rooted`, or `not detected`, including
  the matched evidence that led to the verdict.
- A read-only integrity API route.
- A dashboard integrity view that shows a verdict badge, indicator table, raw
  evidence, and a permanent limitation note.

## Files

- `adb/root_detection.py`
- `routes/root_detection.py`
- `static/js/battery.js`
- `templates/dashboard.html`
- `tests/test_root_detection.py`
- `tests/test_root_detection_routes.py`

## Security And Accuracy Notes

The module is deliberately explicit about its limits: root hiding, Zygisk
DenyList behavior, custom kernels, and shell-UID-specific hiding can defeat
host-side checks. The tool shows evidence; it does not claim authoritative
device attestation.

## Verification

Covered by tests for summary verdict logic, `su` parsing, build-integrity
parsing, partial/missing property handling, and route behavior.

See [`docs/modules/root-detection.md`](modules/root-detection.md) and
[`docs/module-audits/root-detection.md`](module-audits/root-detection.md) for
the permanent module documentation and audit history.
