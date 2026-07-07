# JADX Audit

Files: `adb/jadx_manager.py`, `routes/jadx.py`, `static/js/jadx.js`

Coverage: backend 88%, route 91% (new module, first pass).

Full implementation notes, API reference, and permanent known limitations live in the module
documentation: [`docs/modules/jadx.md`](../modules/jadx.md). This file tracks only what is still
open from the implementation pass.

## Bugs Found And Fixed During Implementation

- `jadx_version()` returned whatever text came out of a failed `jadx --version` invocation (e.g. a
  broken `JAVA_HOME` error message) as if it were a version string, instead of checking the
  subprocess return code first. Fixed to match `adb/apktool_manager.py`'s `_tool_version()`
  convention (return `None` on non-zero exit).
- The exported-component-without-permission finding singularized `"activities"` -> `"activitie"` via
  naive `kind[:-1]` string slicing. Fixed with an explicit plural-to-singular mapping.

## Remaining Items

- None outstanding from this pass. Coverage is in line with other recently-added modules
  (`apktool` had no dedicated audit file at this point in the project's history; `frida`/others sit
  at 87-100%). The uncovered lines are almost entirely defensive `except OSError` branches and a
  handful of platform-specific (`os.name == "nt"`) paths that mirror the same gaps already accepted
  in `adb/manager.py` and `adb/apktool_manager.py`.
