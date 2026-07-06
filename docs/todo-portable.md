# Portable Desktop Build Notes

## Status

Implemented.

The portable build keeps the Flask app as the source of truth and wraps it in a
thin `pywebview` desktop entrypoint plus PyInstaller specs. Web mode continues
to work through `app.py`; desktop mode is additive.

## Implemented Surface

- `requirements-desktop.txt` contains desktop-only GUI/build dependencies.
- `desktop.py` starts the existing Flask app on a free loopback port and opens a
  native webview window once the server is responsive.
- A single-instance lock under writable app data prevents accidental duplicate
  desktop instances.
- `config.py` is frozen-build aware:
  - bundled assets resolve through the PyInstaller extraction/bundle directory;
  - writable state uses per-user app-data locations in frozen builds.
- `app.py` passes explicit template/static folders from `config.py`.
- PyInstaller specs exist for Windows, macOS, and Linux.
- Build scripts support web mode, desktop mode, tests, and platform-local
  PyInstaller builds.
- CI builds per-OS artifacts without cross-compilation.
- Unsigned-build warnings and signing/notarization scope are documented.

## Files

- `desktop.py`
- `requirements-desktop.txt`
- `build/windows.spec`
- `build/macos.spec`
- `build/linux.spec`
- `build/_common.py`
- `build/icons/README.md`
- `scripts/run.ps1`
- `scripts/run.sh`
- `scripts/build-gui.ps1`
- `scripts/build-gui.sh`
- `.github/workflows/desktop-build.yml`
- `tests/test_portable.py`

## Deferred Work

- System tray support.
- Auto-update support.
- Production code-signing and notarization.

Those items need separate design decisions and are intentionally not part of
the v1 portable build.

## Verification

Covered by tests for frozen/non-frozen path resolution, single-instance lock
handling, stale-lock detection, lock release, and free-port selection.

See the README's "Desktop App And Builds" section for user-facing commands.
