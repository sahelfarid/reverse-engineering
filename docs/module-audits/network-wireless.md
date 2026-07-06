# Network And Wireless Audit

Files: `adb/network.py`, `adb/wireless.py`, `routes/network.py`, `static/js/network.js`

Coverage: network 100% (was 21%), wireless 98% (was 27%), route 95% (was 53%).

## Implementation

- Network module reports Wi-Fi IP/prefix, gateway, DNS, mobile network type, Wi-Fi state, ping, forward, and reverse-forward operations.
- Wireless module enables TCP/IP ADB, derives Wi-Fi address, connects/disconnects, and stores known devices in config JSON.
- Hostnames and wireless addresses are regex-limited. Port specs must match `tcp:<number>` or `udp:<number>`.
- Mutating routes require login and CSRF. Forward/reverse and reconnect operations are audit-logged.

## Verified

- `get_network_info()` is covered for full field extraction and the all-missing/failure case.
- `ping_from_device()` is covered for invalid-host rejection and command construction.
- `_validate_port_spec()`, `add_forward()`/`remove_forward()`/`list_forwards()`, and `add_reverse()`/`remove_reverse()`/`list_reverses()` are covered including the new out-of-range-port rejection below.
- `enable_tcpip()`, `get_device_wifi_address()`, `connect()`/`disconnect()` (including out-of-range-port rejection), and the known-device store (`save_known_device()`/`delete_known_device()`/`reconnect_known_devices()`, including the new name validation below) are covered.
- Every mutating route is covered for success + audit-log assertions, including the four routes that were missing audit logging (see below), plus CSRF rejection and `AdbError` mapping.

**Two real gaps found and fixed while writing these tests:**
1. `_PORT_SPEC_RE` (network.py) and `_HOST_PORT_RE` (wireless.py) matched any digit sequence as a port, so `tcp:99999` or `192.168.1.50:999999` passed validation and were only rejected (or not) by the device's own `adb`/`tcpip` handling. Both now parse the port number out of the match and additionally require `0 <= port <= 65535`.
2. Four mutating routes performed real state changes without an audit log entry: `forward_remove`, `reverse_remove`, `wireless_disconnect`, and the known-device save/delete pair (`known_device_save`/`known_device_delete`). All four now call `auth.audit_log()` on success, matching every other mutating route in the app. `known_device_save` only logs when the backend call actually reports `ok: True`, consistent with how validation failures are handled elsewhere.

Also fixed in passing: `save_known_device()` now rejects non-string/blank/overly-long names (same treatment as macro names in the automation module), and `GET /api/devices/<serial>/wireless/address` now catches a malformed `port` query param instead of raising an uncaught `ValueError` (500).

## Gaps And Risks

- Network parsers depend on Android command output format and remain best-effort for OEM variance; this is inherent to `dumpsys`/`ip`/`getprop` scraping and not something more unit tests can fully close.

## Recommended Tests

- None outstanding for this module's Python surface.
