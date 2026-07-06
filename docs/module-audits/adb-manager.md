# ADB Manager Audit

Files: `adb/manager.py`

Coverage: 80% (was 50%).

## Implementation

- Centralizes ADB discovery, bundled platform-tools install, subprocess execution, serial validation, remote-shell quoting, sentinel return-code parsing, and root-shell detection.
- `run()` and `run_binary()` use argv-list subprocess calls and never invoke a host shell.
- `shell()` validates serials and wraps remote commands with an `__RC__` sentinel so device-side shell exit codes are visible even when `adb shell` itself exits cleanly.
- Platform-tools download is isolated behind `download_platform_tools()` and extraction under `config.VENDOR_DIR`.
- `install_adb()` now extracts through a new `_safe_extract()` helper that resolves every archive member against the destination directory and rejects any member (`..` segments, absolute paths) that would land outside it, before calling `zipfile.extractall()`. This closes the zip-slip gap called out below even though the download source is Google's official URL.

## Verified

- Serial validation accepts normal USB and wireless serials and rejects shell metacharacters.
- `quote_remote()` escaping is covered.
- `shell()` sentinel parsing is covered for zero and nonzero remote exit codes.
- ADB lookup precedence is covered for vendor-vs-system ADB.
- `download_platform_tools()` is covered for a successful streamed write and for `requests.RequestException` mapping to `AdbInstallError`.
- `_safe_extract()` is covered for a zip-slip member (rejected, nothing written outside dest) and a normal nested member (extracted correctly).
- `install_adb()` is covered for bad-zip handling and for the "executable missing after extraction" path, both asserting the temp zip is cleaned up.
- `run()` and `run_binary()` are covered for `TimeoutExpired` mapping to `AdbError`.

## Gaps And Risks

- `shell()` assumes callers quote every dynamic remote argument. Several modules do this well, but route-level tests should assert exact command strings for high-risk operations.
- chmod-on-extract behavior (`os.name != "nt"` branch) is still untested since it requires a real extracted file; low risk, standard library call.

## Recommended Tests

- Command-construction tests for modules that pass user-controlled paths into `manager.shell()` (tracked per-module in the other audit files).
- A chmod-branch test using a real temp file to assert the executable bit is set on POSIX.
