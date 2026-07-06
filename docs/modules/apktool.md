# APKTool

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

APK decompile/edit/rebuild workflow for authorized reverse-engineering work. The module pulls an installed APK from a connected device, decompiles it with apktool, exposes a local project browser/editor, rebuilds and signs the result, then reinstalls it through the existing package installer.

## Files

- `adb/apktool_manager.py`
- `routes/apktool.py`
- `static/js/apktool.js`

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/apktool/status` | Java, apktool, signing, zipalign, and debug-keystore status. |
| POST | `/api/apktool/install` | Download/cache the pinned apktool jar. |
| POST | `/api/devices/<serial>/apktool/decompile/<package>` | Start a background decompile job. |
| GET | `/api/apktool/projects` | List local decompiled projects. |
| GET | `/api/apktool/projects/<project>/browse?path=...` | Browse a local decompiled project directory. |
| GET | `/api/apktool/projects/<project>/file?path=...` | Read one project text file. |
| POST | `/api/apktool/projects/<project>/file?path=...` | Save one project text file. |
| POST | `/api/apktool/projects/<project>/rebuild` | Start a background rebuild/sign job. |
| POST | `/api/devices/<serial>/apktool/projects/<project>/reinstall` | Install the latest signed rebuilt APK. |
| DELETE | `/api/apktool/projects/<project>` | Delete a local project directory. |

## Behavior

- Java is detected with `shutil.which("java")` and `java -version`; it is never silently installed.
- The pinned apktool jar is cached under `vendor/apktool/apktool.jar`.
- Decompiled projects live under `workspace/apktool_projects/`; pulled source APKs and rebuilt outputs live under sibling workspace folders.
- File reads/writes resolve against the project root and reject absolute paths, `..` segments, and symlink escapes.
- Rebuilds use argv-list subprocess calls, optional `zipalign`, then `apksigner` or `jarsigner`.
- A debug keystore is generated on first signing use with `keytool`.
- Mutating routes require login, CSRF, and audit logging.

## Known Limitations

- Java/JDK and Android SDK build-tools are host prerequisites; the app can download apktool itself but does not install OS-level runtimes.
- The textarea editor is intentionally simple for v1. It avoids adding a frontend build step or a large code-editor dependency.
- Reinstall uses the latest `rebuilt-signed.apk` for the project.

## Testing

- `tests/test_apktool_manager.py`
- `tests/test_apktool_routes.py`

Coverage includes traversal rejection, symlink escape rejection, status reporting, apktool download behavior, rebuild/sign argv shape, route protection, job creation, and audit logging.
