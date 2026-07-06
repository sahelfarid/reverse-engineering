# Properties Audit

Files: `adb/properties.py`, `routes/properties.py`, `static/js/properties.js`

Coverage: backend 100% (was 92%), route 100% (was 53%).

## Implementation

- Reads `getprop`, parses bracketed lines, categorizes keys with ordered regex rules, and returns sorted categories plus a total count.
- Read-only route requires login but not CSRF.

## Verified

- Category precedence is covered.
- Bracketed `getprop` line parsing is covered, including skipping non-bracketed lines and sorting entries within a category.
- `get_properties()` is covered for the shell-failure -> `AdbError` path.
- Route is covered for success, `AdbNotInstalledError` -> 503, `AdbError` -> 400, and login-required 401.

## Gaps And Risks

- Non-bracketed or OEM-specific lines are skipped silently, which is acceptable for a property viewer and remains documented as best-effort.

## Recommended Tests

- None outstanding for this module's Python surface.
