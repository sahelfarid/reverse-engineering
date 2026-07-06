# Clipboard Audit

Files: `adb/clipboard.py`, clipboard routes in `routes/battery.py`, frontend clipboard tab in dashboard assets.

Coverage: backend 62%, shared route file 51%.

## Implementation

- Clipboard read is best-effort via raw Android clipboard service binder output parsing.
- Clipboard write uses the historical Clipper broadcast convention and clearly reports that a helper app is required.
- Clipboard history is process-local and bounded to 50 entries per serial.
- Write route requires login, CSRF, and audit logging.

## Verified

- Binder reply parser is covered for round-trip text, empty/garbage output, and nonzero exception codes.

## Gaps And Risks

- Android clipboard restrictions make read behavior inherently unreliable on Android 10+.
- In-memory history is not persisted and is not encrypted; this is local process memory only, but clipboard contents can be sensitive.
- Routes are not directly covered.

## Recommended Tests

- Unit tests for `get_clipboard()` success/failure and history deduplication with mocked `manager.shell()`.
- Unit tests for `set_clipboard()` success/failure command construction.
- Route tests for clipboard read/write/history auth and CSRF behavior.
