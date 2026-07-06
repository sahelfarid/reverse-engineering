# ADB Manager Audit

Files: `adb/manager.py`

Coverage: 50%.

## Implementation

- Centralizes ADB discovery, bundled platform-tools install, subprocess execution, serial validation, remote-shell quoting, sentinel return-code parsing, and root-shell detection.
- `run()` and `run_binary()` use argv-list subprocess calls and never invoke a host shell.
- `shell()` validates serials and wraps remote commands with an `__RC__` sentinel so device-side shell exit codes are visible even when `adb shell` itself exits cleanly.
- Platform-tools download is isolated behind `download_platform_tools()` and extraction under `config.VENDOR_DIR`.

## Verified

- Serial validation accepts normal USB and wireless serials and rejects shell metacharacters.
- `quote_remote()` escaping is covered.
- `shell()` sentinel parsing is covered for zero and nonzero remote exit codes.
- ADB lookup precedence is covered for vendor-vs-system ADB.

## Gaps And Risks

- Platform-tools download, zip extraction, chmod, and bad-zip handling are untested.
- `shell()` assumes callers quote every dynamic remote argument. Several modules do this well, but route-level tests should assert exact command strings for high-risk operations.
- `install_adb()` extracts a downloaded zip. Python's `zipfile.extractall()` can be sensitive to malicious zip members if the source were compromised; the source is Google's official URL, but defensive member path validation would reduce supply-chain blast radius.

## Recommended Tests

- Mocked `requests.get()` and `zipfile.ZipFile` tests for successful install, bad zip, network failure, missing executable, and chmod on non-Windows.
- Command-construction tests for modules that pass user-controlled paths into `manager.shell()`.
- Timeout tests for `run()` and `run_binary()` mapping `TimeoutExpired` to `AdbError`.
