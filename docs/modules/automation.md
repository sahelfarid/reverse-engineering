# Automation

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Drives the device UI programmatically: tap, swipe, long-press, text input, keyevents, screen-size queries, and recordable/replayable macros.

## Files

- `adb/automation.py`
- `routes/automation.py`
- `static/js/automation.js`

## API

| Method | Route | Description |
| --- | --- | --- |
| POST | `/api/devices/<serial>/input/tap` | Tap at (x, y). |
| POST | `/api/devices/<serial>/input/swipe` | Swipe between two points. |
| POST | `/api/devices/<serial>/input/long-press` | Long-press (delegates to swipe with dwell). |
| POST | `/api/devices/<serial>/input/text` | Type text; audit-logged with input length. |
| POST | `/api/devices/<serial>/input/keyevent` | Send a keycode. |
| GET | `/api/devices/<serial>/screen-size` | Current screen size. |
| GET | `/api/macros` | List saved macros. |
| POST | `/api/macros` | Save a macro. |
| DELETE | `/api/macros/<name>` | Delete a macro. |
| POST | `/api/devices/<serial>/macros/<name>/play` | Play back a macro's steps. |

## Behavior

- Text input converts spaces to Android's `%s` and quotes the resulting string.
- Keyevent codes are restricted to alphanumeric/underscore values.
- Macro validation caps step count and total wait time; `save_macro()` rejects non-string, blank/whitespace-only, or overly long (>100 char) names.
- Text input and macro changes/playback are audit-logged.
- `tap`/`swipe`/`long-press` route handlers use a shared `_int_field()` helper that catches non-numeric coordinate values and returns a clean 400 instead of an unhandled `ValueError`.

## Known Limitations

- None currently documented for this module's Python surface.

## Testing

- `tests/test_automation.py`
- `tests/test_automation_routes.py`
- Coverage: 100% backend, 98% route

See [`docs/module-audits/automation.md`](../module-audits/automation.md) for the audit history (bugs found and fixed, and any items still open).
