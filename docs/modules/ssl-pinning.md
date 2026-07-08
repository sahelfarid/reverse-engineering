# SSL Pinning Detection & Bypass

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Detects common SSL/TLS pinning implementations in an app (static JADX source/resource scan + a short dynamic Frida observation window) and provides a one-click universal Frida bypass plus a custom bypass-script store, for traffic interception during authorized testing.

## Files

- `adb/ssl_pinning.py`
- `routes/ssl_pinning.py`
- `static/js/ssl-pinning.js` (new "SSL Pinning" tab)

## API

| Method | Route | Description |
| --- | --- | --- |
| POST | `/api/devices/<serial>/packages/<package>/sslpinning/detect` | Static + (by default) dynamic detection report. `dynamic: false` skips the spawn/observe half. CSRF-protected since the dynamic half spawns the app; heavily audit-logged. |
| POST | `/api/devices/<serial>/frida/sslpinning/bypass` | Attaches a bypass script (built-in `universal-trust-manager-bypass` by name, a saved custom script by name, or inline `script_source`) via the shared Frida session registry. Requires `confirm: true` or is rejected with `confirmation_required`. |
| GET | `/api/frida/sslpinning/scripts` | List built-in + saved bypass scripts. |
| POST | `/api/frida/sslpinning/scripts` | Save a custom bypass script. |
| DELETE | `/api/frida/sslpinning/scripts/<name>` | Delete a saved (non-built-in) bypass script. |

## Behavior

- **Static detection**: scans an already-decompiled JADX project (same `project_dir()` lookup as `adb/root_checker.py`) for pinning idioms — OkHttp `CertificatePinner`, custom `X509TrustManager`/`HostnameVerifier` implementations, TrustKit, hardcoded `sha256/...` pin literals — plus a scan of decompiled XML resources for Network Security Config `<pin-set>`/`<pin digest=...>` entries.
- **Dynamic detection**: spawns the app under Frida with an observer script that hooks `okhttp3.CertificatePinner.check`, probes for a loaded TrustKit class, and enumerates loaded classes at runtime to hook any custom `checkServerTrusted` implementation it finds — purely observational (logs a hit, doesn't alter behavior), using the same `frida_manager.drain_messages()` spawn-observe-detach pattern as `root_checker.observe_dynamic()`.
- **Bypass** is a distinct, heavier action: it installs a permissive `X509TrustManager` via an `SSLContext.init` hook and no-ops OkHttp's `CertificatePinner.check` plus `HttpsURLConnection` hostname-verifier setters. It attaches through `adb.frida_manager.attach()` directly, so the resulting session is visible/manageable via the existing `/api/frida/sessions/*` endpoints (list, SSE stream, detach) rather than a parallel session mechanism.
- **Explicit authorization gate**: the bypass route requires `confirm: true` in the request body (a real behavior change to the app's TLS trust, not just an observation) and every bypass attach is audit-logged with the attached script's SHA-256.
- The bypass script store (`data/sslpinning_scripts/`) is separate from `adb/frida_manager.py`'s general script store, but reuses its name-validation (`validate_script_name`) and hashing (`script_hash`) rather than re-implementing them.

## Known Limitations

- Detection patterns are heuristic; obfuscated, native, or custom pinning implementations that don't match these specific idioms won't be flagged by either pass.
- The dynamic observer only sees classes already loaded and checks that fire during the fixed post-spawn window.
- The universal bypass covers OkHttp's `CertificatePinner` and typical custom-`TrustManager`/`HostnameVerifier` patterns; apps with advanced anti-Frida detection or bespoke pinning outside those hooks may not be affected by it, or may crash/detect tampering.
- Requires a working Frida setup (frida-server pushed and running, root) — falls back to static-only detection otherwise, and the bypass route simply fails if Frida can't attach.

## Testing

- `tests/test_ssl_pinning.py`
- `tests/test_ssl_pinning_routes.py`
