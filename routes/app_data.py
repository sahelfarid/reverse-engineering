from flask import Blueprint, jsonify, request

import auth
from adb import app_data
from adb import manager as adb_manager

bp = Blueprint("app_data", __name__)


def _wrap(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except adb_manager.AdbNotInstalledError:
        return None, (jsonify({"ok": False, "error": "adb_not_installed"}), 503)
    except adb_manager.AdbError as exc:
        return None, (jsonify({"ok": False, "error": str(exc)}), 400)


@bp.get("/api/devices/<serial>/packages/<package>/data")
@auth.login_required
def data_index(serial, package):
    scope = request.args.get("scope")
    path = request.args.get("path", "")
    if scope:
        result, err = _wrap(app_data.list_data, serial, package, scope, path)
        if err:
            return err
        return jsonify(result)
    result, err = _wrap(app_data.get_data_overview, serial, package)
    if err:
        return err
    return jsonify({"ok": True, **result})


@bp.get("/api/devices/<serial>/packages/<package>/data/file")
@auth.login_required
def data_file(serial, package):
    path = request.args.get("path", "")
    scope = request.args.get("scope", "private")
    if not path:
        return jsonify({"ok": False, "error": "missing_path"}), 400
    result, err = _wrap(app_data.read_data_file, serial, package, path, scope)
    if err:
        return err
    return jsonify(result)


@bp.get("/api/devices/<serial>/packages/<package>/data/databases")
@auth.login_required
def data_databases(serial, package):
    db_name = request.args.get("db")
    if not db_name:
        result, err = _wrap(app_data.list_databases, serial, package)
        if err:
            return err
        return jsonify(result)

    query = request.args.get("query")
    try:
        max_rows = max(1, min(int(request.args.get("max_rows", 200)), 1000))
    except (TypeError, ValueError):
        max_rows = 200
    result, err = _wrap(app_data.query_database, serial, package, db_name, query, max_rows)
    if err:
        return err
    return jsonify(result)


@bp.post("/api/devices/<serial>/packages/<package>/data/edit")
@auth.login_required
@auth.csrf_protect
def data_edit(serial, package):
    d = request.get_json(silent=True) or {}
    path = d.get("path", "")
    scope = d.get("scope", "private")
    if not path:
        return jsonify({"ok": False, "error": "missing_path"}), 400

    if "key" in d:
        result, err = _wrap(
            app_data.edit_shared_pref_entry, serial, package, path,
            d.get("key", ""), d.get("value"), d.get("value_type", "string"), scope,
        )
    else:
        content = d.get("content")
        if content is None:
            return jsonify({"ok": False, "error": "missing_content"}), 400
        result, err = _wrap(app_data.edit_file, serial, package, path, content, scope)
    if err:
        return err
    auth.audit_log("app_data_edit", {"serial": serial, "package": package, "path": path, "scope": scope})
    return jsonify(result)


@bp.post("/api/devices/<serial>/packages/<package>/data/delete")
@auth.login_required
@auth.csrf_protect
def data_delete(serial, package):
    d = request.get_json(silent=True) or {}
    paths = d.get("paths") or ([d["path"]] if d.get("path") else [])
    scope = d.get("scope", "private")
    if not paths:
        return jsonify({"ok": False, "error": "missing_paths"}), 400
    result, err = _wrap(app_data.delete_data, serial, package, paths, scope)
    if err:
        return err
    auth.audit_log("app_data_delete", {"serial": serial, "package": package, "paths": paths, "scope": scope})
    return jsonify(result)
