# Frida Audit

Files: `adb/frida_manager.py`, `routes/frida.py`, `static/js/frida.js`

Coverage: backend 45%, route 43%.

## Implementation

- Provides Frida Python package status, matching frida-server URL resolution/cache/download, server push/start/stop, Frida process listing with ADB fallback, attach/spawn, message streaming, detach, and script store CRUD.
- Classic frida-server operations require `manager.has_root_shell()`.
- Script names are constrained, default templates are read-only, and script size is capped at 256 KiB.
- Attach audit logs include target, script name, and source hash rather than full source.
- Session registry and message queues are process-local.

## Verified

- ABI-to-arch URL mapping is covered, including unsupported ABI rejection.
- Script store CRUD rejects path traversal and protects default scripts.
- Attach/detach session lifecycle is covered with a mocked `frida` module.

## Gaps And Risks

- Server download/decompression/cache, push, start, stop, status aggregation, and process fallback are not covered.
- `list_processes()` catches all exceptions and falls back to ADB. That is user-friendly but can hide unexpected Frida API failures during debugging.
- Attach target names are not shell-executed, but spawn package names could still benefit from validation for clearer API behavior.
- Stream generators are infinite and heartbeat-based; route-level stream tests are missing.

## Recommended Tests

- Mocked `requests.get()` and `lzma.open()` tests for server download success/failure/cache reuse.
- Mocked `manager.shell()` and `manager.run()` tests for push/start/stop command strings and root-required errors.
- Route tests for script CRUD, attach payload variants, stream error events, detach, CSRF, and audit log entries.
