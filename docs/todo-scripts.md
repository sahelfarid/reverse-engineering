# Script Launchers, README Completion, Commit, and Push

## Summary
Finish the project support layer around the newly added Frida and portable desktop features: replace the generic build GUI with a compact project-aware launcher, add cross-platform run/build scripts, expand `README.md` with current features and commands, verify through a managed environment, then commit and push to `origin/master`.

## Implementation Changes
- Add/replace scripts under `scripts/`:
  - `build-gui.ps1`: compact Windows WinForms launcher with buttons for Install deps, Run web app, Run desktop app, Test, Build Windows desktop, and Stop; include a mode toggle for `.venv` vs active/system Python.
  - `build-gui.sh`: terminal menu for Linux/macOS with the same core actions where applicable.
  - `run.ps1`: Windows CLI runner that supports web mode and desktop mode, defaults to managed `.venv`, and accepts an option to use the active Python environment.
  - `run.sh`: Linux/macOS CLI runner with the same behavior.
- README updates:
  - Document current feature set, including Frida integration and portable desktop packaging.
  - Add quick-start commands for Windows PowerShell, Linux/macOS shell, web mode, desktop mode, tests, and PyInstaller builds.
  - Document script behavior: `.venv` default, active-Python option, build outputs in `dist/`, and platform-specific build constraints.
  - Add Frida notes: requires Python `frida`, rooted device for classic `frida-server`, authorized testing only, local script storage, and server cache locations.
  - Add portable desktop notes: `requirements-desktop.txt`, `desktop.py`, native webview, onefile specs, CI workflow, and unsigned-build warnings.
- TODO docs:
  - Mark implemented portable/frida checklist items as complete only where the repo already contains the corresponding code.
  - Leave genuinely unfinished items unchecked, especially any stretch goals or unimplemented signing/tray/updater work.
- Git workflow:
  - Review `git status` before committing and include the existing Frida changes plus the new script/README/doc updates.
  - Do not touch unrelated untracked or user-owned files unless they are part of this requested script/docs work.
  - Commit with a message like `Add Frida and portable build tooling`.
  - Push the current `master` branch to `origin/master`.

## Test Plan
- Create/reuse `.venv` through the scripts and install `requirements.txt` plus `requirements-desktop.txt`.
- Run `python -m pytest -q`.
- Smoke-check script help/menu behavior:
  - `powershell -ExecutionPolicy Bypass -File scripts/run.ps1 -Help`
  - `powershell -ExecutionPolicy Bypass -File scripts/build-gui.ps1` launches the compact GUI on Windows.
  - `bash scripts/run.sh --help`
  - `bash scripts/build-gui.sh` shows the menu on shell platforms.
- Smoke-check build command wiring without assuming cross-compilation:
  - Windows builds use `pyinstaller build/windows.spec --noconfirm`.
  - macOS/Linux scripts call their matching spec only on the matching OS, with a clear message otherwise.

## Assumptions
- Standardize on “both modes”: scripts default to a managed `.venv`, but expose an option to use active/system Python.
- Push target is `origin master`, matching the current repo state.
- The compact GUI should be practical and project-specific, not a generic arbitrary command runner.
- No code-signing, notarization, tray icon, or auto-updater work is included in this pass.
