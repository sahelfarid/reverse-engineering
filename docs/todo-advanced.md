I’ve appended the missing module documentation from your provided drafts. The four TODO files now include the full detail you supplied—covering real‑time packet inspection, app data management, SSL pinning detection/bypass, and per‑package root detection. The final versions are below.

---

### `todo-network-monitor.md`

```markdown
# Network Monitor (TODO)

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Realtime Android device network packet capture, inspection, filtering, and export (PCAP/Wireshark-compatible). Supports root and non-root paths via VPN simulation, tcpdump, or Frida hooks. Includes per-app filtering, TLS decryption helpers (via SSL pinning bypass integration), live SSE streams, and analysis features.

## Files

- `adb/network_monitor.py`
- `routes/network_monitor.py`
- `static/js/network-monitor.js`

## API (Proposed)

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices/<serial>/network/monitor/status` | Capture tool status and active sessions. |
| POST | `/api/devices/<serial>/network/monitor/start` | Start capture (tcpdump/Frida/PCAPdroid-style, with filters). |
| GET | `/api/devices/<serial>/network/monitor/stream` | SSE stream of live packets (filtered). |
| POST | `/api/devices/<serial>/network/monitor/stop` | Stop capture and save PCAP. |
| GET | `/api/devices/<serial>/network/monitor/capture` | Download PCAP or filtered export. |
| POST | `/api/devices/<serial>/network/monitor/filter` | Apply/update live filters (app, port, protocol, domain, etc.). |

## Behavior

- Leverages existing Frida integration for script-driven hooks or `tcpdump` via root shell (with quoting/safety).
- Non-root fallback via VPN-based capture (e.g., integrate or emulate PCAPdroid logic).
- Filtering on host-side for performance (tag/pid/app/domain/regex) similar to logcat.
- Background job support for long captures; temp storage under `workspace/` with cleanup.
- Export to PCAP; optional integration with Wireshark or mitmproxy for decryption.
- Audit logging for start/stop/export; CSRF for mutations.
- Ties into network-wireless and Frida modules.

## Known Limitations

- Root often required for full packet capture without app cooperation; non-root limited to user-space/VPN methods.
- High-volume traffic can overwhelm streams; needs buffering/throttling.
- TLS decryption requires separate SSL pinning bypass (see related TODO).
- OEM/kernel variations in `tcpdump` availability.

## Testing

- `tests/test_network_monitor.py`
- `tests/test_network_monitor_routes.py`
- Real-device smoke tests for capture/filter/export.
- Coverage targets: 90%+ backend/routes.

See `docs/module-audits/network-monitor.md` (to be created) for audit history.
```

---

### `todo-app-data.md`

```markdown
# App Data Explorer (TODO)

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Browse, list, read, edit, and manage app private data (databases, SharedPreferences, files, cache) with root/run-as awareness. Supports public/external storage too.

## Files

- `adb/app_data.py`
- `routes/app_data.py`
- `static/js/app-data.js`

## API (Proposed)

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices/<serial>/packages/<package>/data` | List data dirs/files (private + public). |
| GET | `/api/devices/<serial>/packages/<package>/data/file?path=...` | Read file (text/DB preview). |
| POST | `/api/devices/<serial>/packages/<package>/data/edit` | Write to file/SharedPrefs/DB entry. |
| POST | `/api/devices/<serial>/packages/<package>/data/delete` | Delete data paths. |
| GET | `/api/devices/<serial>/packages/<package>/data/databases` | List/query SQLite DBs. |

## Behavior

- Uses `run-as <pkg>` + root fallback (like app-inspector).
- SharedPreferences XML/JSON parsing; SQLite query support.
- Path safety (no `..`/absolute escapes, quoting via manager).
- Integrates with files module for upload/download.
- Audit logging + CSRF for mutations; read-only for sensitive paths.

## Known Limitations

- Non-debuggable apps limit `run-as`; root often needed.
- DB editing risky (schema awareness needed).
- Large files/DBs require streaming/pagination.

## Testing

- Unit + real-device tests against system/user apps.
- Coverage: high, including permission/escape cases.

See `docs/module-audits/app-data.md` for audits.
```

---

### `todo-ssl-pinning-detection-and-bypass.md`

```markdown
# SSL Pinning Detection & Bypass (TODO)

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Detect common SSL/TLS pinning implementations in apps and provide one-click Frida-based bypass scripts for traffic interception (integrates with network monitor and mitmproxy setups).

## Files

- `adb/ssl_pinning.py` (or extend frida_manager.py)
- `routes/ssl_pinning.py`
- `static/js/ssl-pinning.js`

## API (Proposed)

| Method | Route | Description |
| --- | --- | --- |
| POST | `/api/devices/<serial>/packages/<package>/sslpinning/detect` | Run static/dynamic detection. |
| POST | `/api/devices/<serial>/frida/sslpinning/bypass` | Attach with universal/custom bypass script. |
| GET | `/api/frida/sslpinning/scripts` | List/store bypass scripts. |

## Behavior

- Static: Scan decompiled sources (via JADX integration) for pinning patterns (e.g., certificate checks, OkHttp, TrustManager).
- Dynamic: Frida script injection (reuse existing sessions).
- Pre-built universal bypass + custom script store.
- Audit all bypass actions heavily; requires explicit authorization.

## Known Limitations

- Detection is heuristic/pattern-based (not exhaustive).
- Bypass may break apps with advanced anti-Frida or custom pinning.
- Requires Frida server; evasion techniques may be needed.

## Testing

- Tests with sample apps having known pinning.
- End-to-end with network capture.

See related Frida/JADX audits.
```

---

### `todo-root-detection-checker-for-packages.md`

```markdown
# Per-Package Root Detection Checker (TODO)

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Checks if an app implements root detection (Magisk detection, Frida checks, safety-net, etc.) using static (JADX) + dynamic (Frida) analysis.

## Files

- `adb/root_checker.py` (extend root_detection.py)
- `routes/root_checker.py`

## API (Proposed)

| Method | Route | Description |
| --- | --- | --- |
| GET/POST | `/api/devices/<serial>/packages/<package>/rootcheck` | Run detection report. |

## Behavior

- Combines JADX source scan + Frida hook results.
- Evidence-based report (similar to root-detection).
- Integrates with app-inspector and JADX.

## Known Limitations

- Evasion possible; best-effort like host root detection.
- Dynamic checks require app launch/attach.

## Testing

- Coverage for common detection patterns.
- Smoke tests on rooted/hidden-root devices.

See `docs/module-audits/...` for details.
```

These now form the complete set of planned modules. All align with existing security boundaries, audit logging, path safety, and testing patterns from `jadx.md`, `frida.md`, `app-inspector.md`, etc. Let me know if you need further adjustments or implementation skeletons.