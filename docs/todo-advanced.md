Remaining module: real-time packet inspection (network monitor). The other three (app data management, SSL pinning detection/bypass, per-package root detection) have been implemented -- see `docs/modules/app-data.md`, `docs/modules/ssl-pinning.md`, and `docs/modules/root-checker.md`.

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

Once network-monitor is implemented, it should align with the existing security boundaries, audit logging, path safety, and testing patterns established by the other three modules (and by `jadx.md`, `frida.md`, `app-inspector.md`).