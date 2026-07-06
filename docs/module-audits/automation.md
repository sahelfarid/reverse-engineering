# Automation Audit

Files: `adb/automation.py`, `routes/automation.py`, `static/js/automation.js`

Coverage: backend 100% (was 39%), route 98% (was 48%).

## Implementation

- Supports tap, swipe, long press, text input, keyevent, screen size, macro save/list/delete, and macro playback.
- Text input converts spaces to Android `%s` and quotes the resulting string.
- Keyevent codes are restricted to alphanumeric/underscore values.
- Macro validation caps step count and total wait time.
- Text and macro changes/playback are audit-logged.

## Verified

- Macro step validation is covered for known types, unknown types, max steps, and excessive wait time.
- `tap()`/`swipe()`/`long_press()` (delegates to `swipe`)/`type_text()` (space->`%s`, quoting) command construction, `get_screen_size()` (override/physical size parsing, failure, no-match), and `keyevent()` (valid + invalid keycode) are all covered.
- `play_macro()` is covered for step execution + overall `ok` aggregation, wait timing with patched `time.sleep()`, a failing step, and pre-flight rejection of invalid steps.
- `list_macros()`/`save_macro()`/`delete_macro()` are covered including the new name validation below.
- Every route is covered: `tap`/`swipe`/`long-press` (success + malformed-coordinate 400s), `text` (audit log with length), `keyevent`, `screen-size`, macro list/save/delete/play (missing fields, `AdbError` mapping, audit logs, macro-not-found 404), and CSRF rejection.

**Two real bugs found and fixed while writing these tests:**
1. `tap`/`swipe`/`long-press` routes passed `d.get("x", 0)` etc. straight into backend functions that call `int(x)` internally. A non-numeric value (or `None`) raised an uncaught `ValueError`/`TypeError`, producing an unhandled 500 instead of a 400. Added a route-level `_int_field()` helper that catches the conversion error and returns `{"ok": False, "error": "invalid_<field>"}` with a 400, used in all three routes.
2. `save_macro()` accepted any JSON-truthy `name` value (including non-string types, since the route only checked `if not name`) with no length bound. Added validation in `adb/automation.py` rejecting non-string, blank/whitespace-only, or overly long (>100 char) names via the existing `AdbError` -> 400 path.

## Gaps And Risks

- None outstanding for this module's Python surface.

## Recommended Tests

- None outstanding.
