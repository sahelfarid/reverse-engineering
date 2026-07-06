# Clipboard Audit

Files: `adb/clipboard.py`, clipboard routes in `routes/battery.py`, frontend clipboard tab in dashboard assets.

Coverage: backend 95% (was 62%), shared route file 100% (was 51%).

## Implementation

- Clipboard read is best-effort via raw Android clipboard service binder output parsing.
- Clipboard write uses the historical Clipper broadcast convention and clearly reports that a helper app is required.
- Clipboard history is process-local and bounded to 50 entries per serial.
- Write route requires login, CSRF, and audit logging.

## Verified

- Binder reply parser is covered for round-trip text, empty/garbage output, and nonzero exception codes.
- `get_clipboard()` is covered for success + history recording, consecutive-duplicate dedup, service-unavailable failure, and unparseable-reply failure. `get_clipboard_history()` is covered for the empty/unknown-serial case.
- `set_clipboard()` is covered for success (Clipper broadcast command construction) and failure.
- `routes/battery.py`'s clipboard endpoints (`clipboard` GET/POST, `clipboard/history`) are covered for success, `AdbError` mapping, CSRF rejection, audit-log assertions, and login-required 401 -- this completes coverage of the whole shared route file (also used by Battery/Hardware and Permissions, both now fully covered too).

## Gaps And Risks

- Android clipboard restrictions make read behavior inherently unreliable on Android 10+ -- inherent platform limitation, not a code bug.
- In-memory history is not persisted and is not encrypted; this is local process memory only, but clipboard contents can be sensitive. Documented tradeoff for a local single-user tool, unchanged.

## Recommended Tests

- None outstanding for this module's Python surface.
