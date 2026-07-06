# Properties

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Read-only viewer over `getprop`, with keys grouped into human-meaningful categories.

## Files

- `adb/properties.py`
- `routes/properties.py`
- `static/js/properties.js`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices/<serial>/properties` | Categorized property list + total count. |

## Behavior

- Reads `getprop`, parses bracketed lines, categorizes keys with ordered regex rules, and returns sorted categories plus a total count.
- The read-only route requires login but not CSRF.

## Known Limitations

- Non-bracketed or OEM-specific lines are skipped silently, which is acceptable for a property viewer.

## Testing

- `tests/test_properties.py`
- `tests/test_properties_routes.py`
- Coverage: 100% backend, 100% route

See [`docs/module-audits/properties.md`](../module-audits/properties.md) for the audit history (bugs found and fixed, and any items still open).
