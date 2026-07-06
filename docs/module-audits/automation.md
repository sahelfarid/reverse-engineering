# Automation Audit

Files: `adb/automation.py`, `routes/automation.py`, `static/js/automation.js`

Coverage: backend 39%, route 48%.

## Implementation

- Supports tap, swipe, long press, text input, keyevent, screen size, macro save/list/delete, and macro playback.
- Text input converts spaces to Android `%s` and quotes the resulting string.
- Keyevent codes are restricted to alphanumeric/underscore values.
- Macro validation caps step count and total wait time.
- Text and macro changes/playback are audit-logged.

## Verified

- Macro step validation is covered for known types, unknown types, max steps, and excessive wait time.

## Gaps And Risks

- Coordinate and duration values are coerced with `int()` in backend functions. Bad route input can raise instead of producing a 400 response.
- Macro names are not validated. They are JSON keys rather than filesystem paths, but validation would keep UI and API behavior predictable.
- Macro playback device calls are not mocked in tests.

## Recommended Tests

- Unit tests for tap/swipe/text/keyevent command construction.
- Route tests for malformed coordinate/duration payloads and macro CRUD.
- Macro playback tests for wait timing with patched `time.sleep()` and mixed success/failure steps.
