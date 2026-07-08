# Per-Package Root Detection Checker

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Checks whether a specific app implements root detection, using static (JADX source pattern scan) and dynamic (Frida runtime observation) analysis. Complements [`docs/modules/root-detection.md`](root-detection.md) (device-level "is this rooted") with an app-level "does this app try to detect root".

## Files

- `adb/root_checker.py`
- `routes/root_checker.py`
- Wired into the App Inspector tab (`static/js/inspector.js`) as a "Root check" sub-nav view — no dedicated JS file.

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices/<serial>/packages/<package>/rootcheck` | Static-only report (JADX source scan of an already-decompiled project). Read-only, no CSRF. |
| POST | `/api/devices/<serial>/packages/<package>/rootcheck` | Static + dynamic report: spawns the app under Frida with an observer script for `duration_sec` (clamped 1-15s, default 4s), then detaches. Has side effects (restarts the app), so it's CSRF-protected and audit-logged. |

## Behavior

- **Static**: scans an already-decompiled JADX project for the package (`adb/jadx_manager.py`'s `project_dir()`) line-by-line for root-check idioms — su path strings, `Runtime.exec("su ...")`, RootBeer/RootCloak libraries, Magisk/SuperSU package lookups, SafetyNet/Play Integrity references, and common method names like `isRooted`/`checkRoot`. Returns `{"available": False, "reason": ...}` rather than decompiling on demand — a "run a quick check" endpoint shouldn't silently kick off a slow jadx job.
- **Dynamic**: spawns the target package via `adb.frida_manager.attach()` with a dedicated observer script that hooks `File.exists()`, `Runtime.exec()`, and `PackageManager.getPackageInfo()` for the same idioms, collects whatever fires via the new `frida_manager.drain_messages(session_id, duration_sec)` helper (a fixed-window queue drain, distinct from `stream_messages()`'s infinite SSE generator), then detaches. Purely observational — no return values are altered, so this is not a bypass.
- `summarize()` produces a verdict (`no root detection evidence found` / `root detection likely implemented` / `root detection implemented (static + dynamic evidence)`) plus the full list of matched indicators, the same evidence-first shape as `root_detection.summarize()`.
- Any Frida attach failure (no frida-server, no root, spawn failure) is caught and reported in the response rather than raised, so the static half of the report still comes back.

## Known Limitations

- Static patterns are heuristic and only run against whatever JADX has already decompiled; obfuscated, native (JNI), or reflection-based checks can miss both the static and dynamic passes entirely.
- Dynamic observation only sees what happens to fire during the fixed window right after spawn; checks gated behind user interaction or a timer won't be observed.
- Requires a working Frida setup (frida-server pushed and running, root) for the dynamic half; falls back to static-only otherwise.

## Testing

- `tests/test_root_checker.py`
- `tests/test_root_checker_routes.py`
- `tests/test_frida_manager.py` covers the new `drain_messages()` helper.
