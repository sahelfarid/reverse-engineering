# Frida Implementation Notes

## Status

Implemented.

The Frida workflow adds authorized dynamic instrumentation for rooted Android
test devices. It manages the matching `frida-server` binary, starts/stops it on
the device, attaches to or spawns target processes, injects JavaScript, streams
script output, and persists user scripts locally.

## Implemented Surface

- Python `frida` import is lazy, so the app still boots when Frida is not
  installed.
- Device ABI is mapped to the correct Frida Android server archive.
- Matching `frida-server` binaries are downloaded and cached under
  `vendor/frida/<version>/<abi>/`.
- Server push/start/stop uses `/data/local/tmp/frida-server` and root-shell
  checks through the shared ADB manager.
- Process listing uses the Frida Python API with an ADB process-list fallback.
- Attach/spawn sessions are tracked in memory, with unload/detach cleanup.
- Session messages are streamed to the browser with SSE.
- User scripts live under `data/frida_scripts/`; starter templates are
  read-only and framed for authorized testing.
- Mutating routes require login, CSRF protection, and audit logging.
- The dashboard has a Frida tab with server controls, target selection, a
  script editor, templates, session controls, and a live console.

## Files

- `adb/frida_manager.py`
- `routes/frida.py`
- `static/js/frida.js`
- `templates/dashboard.html`
- `requirements.txt`
- `tests/test_frida_manager.py`
- `tests/test_frida_routes.py`

## Security Notes

Frida is powerful because it executes JavaScript inside a target process. The
UI, starter scripts, and route audit logs are intentionally framed around apps
and devices the operator owns or is explicitly authorized to test.

Classic `frida-server` requires a rooted device. Non-root Frida Gadget APK
repackaging is intentionally out of scope for this implementation.

## Verification

Covered by unit/route tests for ABI mapping, script-store CRUD, traversal-like
script name rejection, mocked attach/detach lifecycle, and route protection.

See [`docs/modules/frida.md`](modules/frida.md) and
[`docs/module-audits/frida.md`](module-audits/frida.md) for the permanent module
documentation and audit history.
