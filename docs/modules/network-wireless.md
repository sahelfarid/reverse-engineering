# Network And Wireless

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Wi-Fi/network status, port forwarding/reverse-forwarding, and wireless (TCP/IP) ADB connection management, including a small store of known wireless devices.

## Files

- `adb/network.py`
- `adb/wireless.py`
- `routes/network.py`
- `static/js/network.js`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices/<serial>/network` | Wi-Fi/mobile network detail. |
| POST | `/api/devices/<serial>/network/ping` | Ping a host from the device. |
| GET | `/api/forwards` | List active adb forwards. |
| POST | `/api/devices/<serial>/forward` | Add a forward. |
| POST | `/api/forward/remove` | Remove a forward. |
| GET | `/api/devices/<serial>/reverse` | List active reverse forwards. |
| POST | `/api/devices/<serial>/reverse` | Add a reverse forward. |
| POST | `/api/devices/<serial>/reverse/remove` | Remove a reverse forward. |
| POST | `/api/devices/<serial>/wireless/enable-tcpip` | Switch the device to TCP/IP ADB. |
| GET | `/api/devices/<serial>/wireless/address` | Derive the device's Wi-Fi ADB address. |
| POST | `/api/wireless/connect` | Connect to a host:port over wireless ADB. |
| POST | `/api/wireless/disconnect` | Disconnect a wireless ADB address. |
| GET | `/api/wireless/known` | List saved known devices. |
| POST | `/api/wireless/known` | Save a known device. |
| DELETE | `/api/wireless/known/<name>` | Delete a known device. |
| POST | `/api/wireless/reconnect-all` | Reconnect all saved known devices. |

## Behavior

- The network module reports Wi-Fi IP/prefix, gateway, DNS, mobile network type, Wi-Fi state, ping, forward, and reverse-forward operations.
- The wireless module enables TCP/IP ADB, derives the Wi-Fi address, connects/disconnects, and stores known devices in config JSON.
- Hostnames and wireless addresses are regex-limited. Port specs must match `tcp:<number>` or `udp:<number>`, and the parsed port number must additionally satisfy `0 <= port <= 65535`.
- All mutating routes require login and CSRF. Forward/reverse-remove, wireless disconnect, and known-device save/delete are all audit-logged (this closed a gap where four mutating routes performed real state changes with no audit entry).
- `save_known_device()` rejects non-string/blank/overly-long names, matching the macro-name validation pattern in the Automation module.

## Known Limitations

- Network parsers depend on Android command output format and remain best-effort for OEM variance; inherent to `dumpsys`/`ip`/`getprop` scraping, not something more unit tests can fully close.

## Testing

- `tests/test_network.py`
- `tests/test_wireless.py`
- `tests/test_network_routes.py`
- Coverage: network 100%, wireless 98%, routes/network 95%

See [`docs/module-audits/network-wireless.md`](../module-audits/network-wireless.md) for the audit history (bugs found and fixed, and any items still open).
