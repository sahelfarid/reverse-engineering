# Permissions Audit

Files: `adb/permissions.py`, permission routes in `routes/battery.py`, frontend permission tab in dashboard assets.

Coverage: backend 35%, shared route file 51%.

## Implementation

- Validates permission strings, classifies dangerous permissions, reads package permissions through app inspector, and grants/revokes permissions with `pm grant`/`pm revoke`.
- Package and permission values are validated before shell use and quoted in grant/revoke commands.
- Grant/revoke routes require login, CSRF, and audit logging.

## Verified

- Permission module has no direct tests. Behavior is indirectly constrained by app inspector/package validation shape.

## Gaps And Risks

- `_PERMISSION_RE` allows broad custom permission names, which is useful for app-defined permissions but should be intentionally documented.
- Grant/revoke parser only returns `stderr` on failure; some Android builds emit useful failure text on stdout.
- Permission detail depends on app inspector parser, which is under-tested.

## Recommended Tests

- Unit tests for permission validation, dangerous/normal classification, and grant/revoke command construction.
- Route tests for missing permission field, invalid permission, CSRF, and audit logging.
