# Permissions Audit

Files: `adb/permissions.py`, permission routes in `routes/battery.py`, frontend permission tab in dashboard assets.

Coverage: backend 100% (was 35%), shared route file 100% (was 51%).

## Implementation

- Validates permission strings, classifies dangerous permissions, reads package permissions through app inspector, and grants/revokes permissions with `pm grant`/`pm revoke`.
- Package and permission values are validated before shell use and quoted in grant/revoke commands.
- Grant/revoke routes require login, CSRF, and audit logging.

## Verified

- `validate_permission()` is covered for standard and app-defined custom names, and for rejecting empty/shell-metacharacter values.
- `get_permission_detail()` is covered for dangerous/normal classification.
- `grant_permission()`/`revoke_permission()` are covered for success, stderr-based failure, and the stdout-fallback case below; both are also covered for validating the permission name before ever calling `manager.shell()`.
- Routes are covered for `permissions` detail (success + `AdbError` mapping), `permissions/grant` and `permissions/revoke` (success + audit log, invalid-permission mapping, CSRF rejection), and login-required 401.

**A real bug found and fixed while writing these tests:** `grant_permission()`/`revoke_permission()` only ever reported `stderr` on failure, discarding `stdout` even when it was empty. Some Android/OEM `pm` builds print failure text (e.g. `Failure: SecurityException`) to stdout rather than stderr, which meant those failures surfaced as `{"ok": false, "error": null-ish/empty}` instead of a useful message. Fixed to fall back to stdout when stderr is empty, matching the `(stdout + stderr)` pattern already used elsewhere in the codebase (e.g. `adb/packages.py`'s `_pm_action`).

## Gaps And Risks

- `_PERMISSION_RE` allows broad custom permission names, which is useful for app-defined permissions; documented here as intentional rather than a gap.
- Permission detail still depends on the app inspector parser's `dumpsys package` scraping, which is now itself fully covered (see the App Inspector audit) but remains best-effort for OEM format variance.

## Recommended Tests

- None outstanding for this module's Python surface.
