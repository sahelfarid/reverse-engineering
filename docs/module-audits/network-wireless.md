# Network And Wireless Audit

Files: `adb/network.py`, `adb/wireless.py`, `routes/network.py`, `static/js/network.js`

Coverage: network 21%, wireless 27%, route 53%.

## Implementation

- Network module reports Wi-Fi IP/prefix, gateway, DNS, mobile network type, Wi-Fi state, ping, forward, and reverse-forward operations.
- Wireless module enables TCP/IP ADB, derives Wi-Fi address, connects/disconnects, and stores known devices in config JSON.
- Hostnames and wireless addresses are regex-limited. Port specs must match `tcp:<number>` or `udp:<number>`.
- Mutating routes require login and CSRF. Forward/reverse and reconnect operations are audit-logged.

## Verified

- Current tests do not directly cover network or wireless modules.

## Gaps And Risks

- Port validators accept any digits and do not enforce 1..65535.
- Wireless known-device names are not validated; they are JSON keys, not paths, but validation would improve API predictability.
- Network parsers depend on Android command output and are untested.
- Some mutating network routes are not audit-logged, such as forward remove, reverse remove, wireless disconnect, and known-device save/delete.

## Recommended Tests

- Unit tests for port validation, host validation, and wireless address validation including out-of-range ports.
- Mocked parser tests for `ip addr`, `ip route`, DNS props, and Wi-Fi state.
- Flask client tests for each mutating route, CSRF rejection, and audit log expectations.
