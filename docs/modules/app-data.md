# App Data Explorer

## Table Of Contents

- [Overview](#overview)
- [Files](#files)
- [API](#api)
- [Behavior](#behavior)
- [Known Limitations](#known-limitations)
- [Testing](#testing)

## Overview

Browse, preview, edit, and delete an app's private data (`/data/data/<package>`: databases, SharedPreferences, files, cache) and public external storage (`/sdcard/Android/data/<package>`), with the same run-as/root-fallback awareness as App Inspector.

## Files

- `adb/app_data.py`
- `routes/app_data.py`
- `static/js/app-data.js` (new "App Data" tab, alongside App Inspector)

## API

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/devices/<serial>/packages/<package>/data` | No `scope` param: overview of both scopes' top-level accessibility. With `scope` (+ optional `path`): browse that directory. |
| GET | `/api/devices/<serial>/packages/<package>/data/file?path=...&scope=...` | Read a file: text/JSON/shared_prefs preview, or base64 for anything that doesn't look like text. `.db`/`.sqlite` files short-circuit to a pointer at the databases endpoint instead of being read as a blob. |
| POST | `/api/devices/<serial>/packages/<package>/data/edit` | Body with `content` overwrites a whole file; body with `key`/`value`/`value_type` updates one SharedPreferences entry (reads the XML, replaces/inserts that `<name>` element, writes it back). |
| POST | `/api/devices/<serial>/packages/<package>/data/delete` | Body `paths: [...]` (or single `path`) + `scope`; `rm -rf`s each, refusing to resolve to the scope root itself. |
| GET | `/api/devices/<serial>/packages/<package>/data/databases` | No `db` param: list `*.db`/`*.sqlite`/`*.sqlite3` files under `databases/`. With `db` (+ optional `query`, `max_rows`): pulls the DB to a local temp file and opens it read-only. |

## Behavior

- **Scopes**: `private` (`/data/data/<package>`, via `run-as` falling back to `su -c`) and `public` (`/sdcard/Android/data/<package>`, plain shell — no elevated access usually needed).
- **Binary safety**: adb shell is a text pipe, so any read/write of file contents goes through `base64`/`base64 -d` on-device rather than raw text — required for SQLite DBs and arbitrary binaries, not just an optimization.
- **`su -c` quoting**: the root fallback re-quotes the *entire* command string as one opaque argument via `manager.quote_remote()` rather than hand-wrapping it in `'...'` — safe even when the command already contains quoted fragments (e.g. a path with a space).
- **SQL queries**: DB files are pulled to a local temp file and opened with Python's `sqlite3` in `mode=ro` (read-only URI). Only `SELECT` statements are allowed (regex-gated), and the read-only connection is a second layer of defense even if that gate were bypassed. No on-device row editing — see limitations.
- **SharedPreferences**: parsed from Android's `<map>` XML format (`string` uses element text; `boolean`/`int`/`long`/`float` use a `value` attribute; `set` is a list of nested `string`s). Editing one entry replaces any existing element with that `name` and appends the new one, then re-serializes the whole file.
- Path safety: every relative path is validated against `..`/absolute-path escapes before being joined onto a scope's base directory (mirrors `adb/jadx_manager.py`'s project-path guard, adapted for remote device paths instead of local ones).
- Mutating routes (`edit`, `delete`) are CSRF-protected and audit-logged; read routes are not.

## Known Limitations

- Non-debuggable apps limit `run-as`; without root, private data is inaccessible (the API reports this explicitly via `accessible: false` + `limitation`).
- In-place file/SharedPreferences writes are capped at 512KB (sent as a single base64 `echo | base64 -d >` shell command) — no chunked/streaming upload path.
- No on-device SQL write support: query is `SELECT`-only against a local read-only copy of the DB. Editing individual rows would require schema-aware UPDATE generation, which is out of scope for this pass.
- SharedPreferences rewrites go through `ElementTree`, so the exact byte-for-byte formatting Android's own writer produces (e.g. the `standalone='yes'` XML declaration) isn't preserved — the file remains valid, parseable XML.
- Large files/DBs are read in full (up to a byte cap) rather than paginated/streamed.

## Testing

- `tests/test_app_data.py`
- `tests/test_app_data_routes.py`
