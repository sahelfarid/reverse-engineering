# Script Launchers And README Notes

## Status

Implemented.

The project has cross-platform run/build helpers and README coverage for web
mode, desktop mode, tests, PyInstaller builds, Frida, and portable packaging.

## Implemented Surface

- `scripts/run.ps1` provides Windows CLI actions for web, desktop, tests, and
  platform-local builds.
- `scripts/run.sh` provides the same core actions for Linux/macOS shells.
- Scripts default to a managed `.venv` but can use the active/system Python.
- Desktop dependency installation is opt-in through the script flags.
- `scripts/build-gui.ps1` exposes a compact Windows launcher for common
  project actions.
- `scripts/build-gui.sh` exposes a shell menu with matching actions.
- Build commands use the matching platform spec and document PyInstaller's
  no-cross-compilation constraint.
- The README documents current features, quick starts, desktop builds, Frida,
  security posture, development commands, and troubleshooting.

## Files

- `scripts/run.ps1`
- `scripts/run.sh`
- `scripts/build-gui.ps1`
- `scripts/build-gui.sh`
- `README.md`
- `requirements-desktop.txt`
- `desktop.py`
- `build/*.spec`

## Verification

The launcher behavior is intentionally thin around existing commands. The
recommended smoke checks are:

```sh
sh scripts/run.sh --help
sh scripts/build-gui.sh
sh scripts/run.sh test
```

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run.ps1 -Help
powershell -ExecutionPolicy Bypass -File scripts/build-gui.ps1
powershell -ExecutionPolicy Bypass -File scripts/run.ps1 -Action test
```

See the README for the stable user-facing command reference.
