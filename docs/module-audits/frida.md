# Frida Audit

Files: `adb/frida_manager.py`, `routes/frida.py`, `static/js/frida.js`

Coverage: backend 87% (was 45%), route 97% (was 43%).

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
- `ensure_frida_server()` is covered for download+decompress+temp-file cleanup, cache reuse (no network call when already present), missing-frida-package rejection, and download-failure cleanup.
- `push_server()`/`start_server()`/`push_and_start_server()`/`stop_server()` are covered for the root-required guard, success, push-needed-first wiring, already-running short-circuit, start-command failure, no-pid-reported failure, and stop success/failure (including the stderr-vs-generic-message fallback).
- `get_status()` is covered for multi-device aggregation (excluding non-`device`-state entries), `list_devices()` failure producing an empty device list, and per-device error capture.
- `list_processes()` is covered for the Frida-device path and the ADB fallback path when the Frida API raises.
- `stream_messages()` is covered for unknown-session rejection and the queued-message-then-heartbeat sequence (using a fake non-blocking queue to avoid the real 15s `get()` timeout in tests).
- `script_hash()` is covered for stability and distinctness.
- Every route is covered: status, server push/start/stop (success + audit log + CSRF + `AdbError` mapping), processes, attach (missing source, unknown script name, script-name resolution, inline source + spawn target, `AdbError` mapping -- and confirms full script source is never included in the audit log, only its sha256), sessions list, stream (SSE data + error framing), detach, and script CRUD (save/delete, confirms source is never audit-logged either).

## Gaps And Risks

- `list_processes()` still catches all exceptions and falls back to ADB. That remains intentionally user-friendly (a Frida-side USB/device-manager hiccup shouldn't break the process list), and is now covered for both paths rather than being an untested judgment call.
- Attach target names are not shell-executed (this whole module talks to the `frida` Python API, not device shell strings for attach targets), so there's no injection surface to validate there beyond what's already covered.

## Recommended Tests

- None outstanding for this module's Python surface.
