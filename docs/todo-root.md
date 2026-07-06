# TODO: Root detection & device integrity indicators

## Objective

Add a device-trust/integrity panel: check whether the connected device is
rooted and surface other tamper/integrity indicators (verified boot state,
bootloader lock, SELinux mode, debuggable build), so a report of "what was
this device's state during testing" can be produced. This complements
`adb/manager.py:has_root_shell()` (already used by several modules to decide
whether a root-only action is available) with a fuller, transparent
checklist rather than a single boolean.

Builds on existing code — do not duplicate:
- `adb/manager.py:has_root_shell()` — the authoritative "can we get a root shell right now" check;
  this module explains *why* (or why not) with corroborating evidence, it doesn't replace it.
- `adb/devices.py:get_basic_properties()` pattern for reading `getprop` keys.
- `adb/packages.py:list_packages()`/`_parse_dumpsys_packages()` for the Magisk-app-installed check
  (don't re-run a second full `dumpsys package packages` dump — accept a packages list as an argument,
  or query just the one package via `pm path com.topjohnwu.magisk`).
- `adb/properties.py`'s categorized getprop view already surfaces `ro.build.tags`,
  `ro.boot.verifiedbootstate`, etc. individually; this module interprets them together.

## Indicators to implement (each: boolean + raw evidence string, never a bare boolean with no evidence)

- [ ] **su binary presence** — check common paths via one batched shell call:
      `for p in /system/bin/su /system/xbin/su /sbin/su /system/sd/xbin/su /data/local/xbin/su
      /data/local/bin/su /system/bin/failsafe/su /system/usr/we-need-root/su /su/bin/su; do
      [ -e "$p" ] && echo "$p"; done` — one round trip instead of N.
- [ ] **Working root shell** — reuse `manager.has_root_shell(serial)` directly (`su -c id` returns
      `uid=0`); this is the strongest signal and should be weighted accordingly in the summary.
- [ ] **Magisk app installed** — `pm path com.topjohnwu.magisk` (exit 0 = installed); note that Magisk
      can hide itself from `pm list packages` for specific target apps (Magisk Hide / DenyList) but
      generally still resolves via direct `pm path` unless the *shell* UID itself is on the deny list,
      which is rare — document this nuance rather than overclaiming reliability.
- [ ] **Magisk filesystem artifacts** — `/sbin/.magisk`, `/cache/magisk.log`,
      `/data/adb/magisk` existence checks (same batched-`test` pattern as the su-path check).
- [ ] **Busybox presence** — `which busybox` (commonly installed alongside root, not proof by itself —
      surface as a weak/corroborating signal, not a standalone verdict).
- [ ] **Build tags** — `getprop ro.build.tags`: `test-keys` (custom/dev-signed build — common on rooted
      or custom ROMs) vs `release-keys` (stock).
- [ ] **Debuggable / secure flags** — `getprop ro.debuggable` (`1` = debuggable build) and
      `getprop ro.secure` (`0` = less restricted userdebug/eng build).
- [ ] **Verified boot state** — `getprop ro.boot.verifiedbootstate` (`green`/`yellow`/`orange`/`red`) and
      `getprop ro.boot.flash.locked` (`1` locked / `0` unlocked bootloader) — an unlocked bootloader is
      the precondition for most rooting methods and is independently meaningful even without su present.
- [ ] **SELinux mode** — `getenforce` (`Enforcing` vs `Permissive`/`Disabled` — the latter two are a
      strong integrity red flag on a production device).
- [ ] **Known root-cloaking limitation** — explicitly document (in both code comments and the UI) that
      sophisticated hiding (Magisk Hide/Zygisk DenyList scoped to the shell UID, or a custom kernel that
      only exposes root to specific UIDs) can defeat *all* of the above from an adb-shell vantage point.
      The only authoritative check is Google's own **Play Integrity API** (successor to SafetyNet), which
      must be evaluated from inside an app on-device, not from the host — this tool cannot and should
      not claim to replace it. Say this plainly rather than presenting a false sense of certainty.

## Module: `adb_toolkit/root_detection.py`

- [ ] `check_su_paths(serial) -> list[str]` — batched `test -e` loop, returns matched paths.
- [ ] `check_magisk(serial) -> dict` — app-installed bool + filesystem-artifact matches.
- [ ] `check_build_integrity(serial) -> dict` — build tags, debuggable, secure, verified boot state,
      bootloader lock, SELinux mode — all via `getprop`/`getenforce` (batch into one `shell()` call
      joined with `;` and split on a delimiter, same sentinel-splitting idea as `manager.shell()`, to
      avoid N round trips for N properties).
- [ ] `summarize(indicators: dict) -> dict` — produce a verdict string
      (`"rooted"` / `"likely rooted"` / `"not detected"`) plus the *list* of matched indicators that led
      to it — never collapse to a single opaque boolean; the UI must show its work.
- [ ] `get_integrity_report(serial) -> dict` — orchestrates all of the above into one response shape.

## Routes: `routes/root_detection.py`

- [ ] `GET /api/devices/<serial>/integrity` — returns the full report from `get_integrity_report()`.
      Read-only (no state changes), so no CSRF needed — same treatment as `routes/properties.py`.

## Frontend

- [ ] New "Integrity" tab (or a sub-section added to the existing Battery/HW tab, given how related
      "device trust" is to hardware/build info — pick whichever keeps the sidebar from getting too long;
      Battery/HW tab is the better fit since `adb/battery.py` already surfaces build-adjacent facts).
- [ ] Overall verdict badge (green="not detected" / yellow="likely rooted" / red="rooted") followed by
      a checklist table of every individual indicator with ✓/✗ and its raw evidence string — mirrors the
      "best effort, show your work" pattern already used for unparseable `ls`/`ps` lines elsewhere in
      this app.
- [ ] A permanent, non-dismissible note under the verdict: "This is host-side, best-effort detection;
      sophisticated root-hiding can defeat it. It does not replace Play Integrity/SafetyNet."

## Tests to add

- [ ] `summarize()` verdict logic across a matrix of indicator combinations (all-clear, su-only,
      Magisk-app-only, build-tags-only, everything-positive) with mocked indicator dicts — pure function,
      no subprocess needed.
- [ ] `check_su_paths`/`check_build_integrity` parsing with mocked `manager.shell()` output, including a
      partial-failure case (some `getprop` calls succeed, others return empty) to confirm one missing
      property doesn't null out the whole report (same graceful-degradation standard as the rest of the
      codebase).
