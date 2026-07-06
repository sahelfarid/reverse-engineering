# Properties Audit

Files: `adb/properties.py`, `routes/properties.py`, `static/js/properties.js`

Coverage: backend 92%, route 53%.

## Implementation

- Reads `getprop`, parses bracketed lines, categorizes keys with ordered regex rules, and returns sorted categories plus a total count.
- Read-only route requires login but not CSRF.

## Verified

- Category precedence is covered.
- Bracketed `getprop` line parsing is covered.

## Gaps And Risks

- Route error mapping is not directly covered.
- Non-bracketed or OEM-specific lines are skipped silently, which is acceptable for a property viewer but should remain documented as best-effort.

## Recommended Tests

- Flask client tests for successful property response and `AdbNotInstalledError`/`AdbError` mapping.
- Parser fixture for duplicate categories and unusual empty values.
