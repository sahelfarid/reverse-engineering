import json
from unittest.mock import patch

from adb import manager as adb_manager


# --- GET /data (overview vs scoped browse) --------------------------------

def test_data_index_without_scope_returns_overview(auth_client):
    with patch("routes.app_data.app_data.get_data_overview", return_value={"package": "com.example.app", "private": {}, "public": {}}) as mock_overview:
        res = auth_client.get("/api/devices/s1/packages/com.example.app/data")
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["package"] == "com.example.app"
    mock_overview.assert_called_once_with("s1", "com.example.app")


def test_data_index_with_scope_browses_that_scope(auth_client):
    with patch("routes.app_data.app_data.list_data", return_value={"ok": True, "scope": "private", "path": "databases", "entries": []}) as mock_list:
        res = auth_client.get("/api/devices/s1/packages/com.example.app/data?scope=private&path=databases")
    assert res.status_code == 200
    mock_list.assert_called_once_with("s1", "com.example.app", "private", "databases")


def test_data_index_requires_login(client):
    assert client.get("/api/devices/s1/packages/com.example.app/data").status_code == 401


def test_data_index_maps_adb_error(auth_client):
    with patch("routes.app_data.app_data.get_data_overview", side_effect=adb_manager.AdbError("bad")):
        res = auth_client.get("/api/devices/s1/packages/com.example.app/data")
    assert res.status_code == 400


def test_data_index_maps_adb_not_installed(auth_client):
    with patch("routes.app_data.app_data.get_data_overview", side_effect=adb_manager.AdbNotInstalledError("x")):
        res = auth_client.get("/api/devices/s1/packages/com.example.app/data")
    assert res.status_code == 503


# --- GET /data/file ----------------------------------------------------------

def test_data_file_requires_path(auth_client):
    res = auth_client.get("/api/devices/s1/packages/com.example.app/data/file")
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_path"


def test_data_file_success(auth_client):
    with patch("routes.app_data.app_data.read_data_file", return_value={"ok": True, "kind": "text", "content": "hi"}) as mock_read:
        res = auth_client.get("/api/devices/s1/packages/com.example.app/data/file?path=files/notes.txt&scope=public")
    assert res.status_code == 200
    mock_read.assert_called_once_with("s1", "com.example.app", "files/notes.txt", "public")


def test_data_file_defaults_to_private_scope(auth_client):
    with patch("routes.app_data.app_data.read_data_file", return_value={"ok": True}) as mock_read:
        auth_client.get("/api/devices/s1/packages/com.example.app/data/file?path=files/notes.txt")
    assert mock_read.call_args.args[3] == "private"


# --- GET /data/databases -------------------------------------------------------

def test_data_databases_lists_without_db_param(auth_client):
    with patch("routes.app_data.app_data.list_databases", return_value={"ok": True, "databases": ["a.db"]}) as mock_list:
        res = auth_client.get("/api/devices/s1/packages/com.example.app/data/databases")
    assert res.status_code == 200
    mock_list.assert_called_once_with("s1", "com.example.app")


def test_data_databases_queries_with_db_param(auth_client):
    with patch("routes.app_data.app_data.query_database", return_value={"ok": True, "tables": ["users"]}) as mock_query:
        res = auth_client.get("/api/devices/s1/packages/com.example.app/data/databases?db=a.db&query=SELECT+*+FROM+users&max_rows=50")
    assert res.status_code == 200
    mock_query.assert_called_once_with("s1", "com.example.app", "a.db", "SELECT * FROM users", 50)


def test_data_databases_clamps_max_rows(auth_client):
    with patch("routes.app_data.app_data.query_database", return_value={"ok": True}) as mock_query:
        auth_client.get("/api/devices/s1/packages/com.example.app/data/databases?db=a.db&max_rows=99999")
    assert mock_query.call_args.args[4] == 1000


def test_data_databases_maps_adb_error(auth_client):
    with patch("routes.app_data.app_data.list_databases", side_effect=adb_manager.AdbError("bad")):
        res = auth_client.get("/api/devices/s1/packages/com.example.app/data/databases")
    assert res.status_code == 400


# --- POST /data/edit -----------------------------------------------------------

def test_data_edit_file_content(auth_client):
    with patch("routes.app_data.app_data.edit_file", return_value={"ok": True}) as mock_edit:
        res = auth_client.post(
            "/api/devices/s1/packages/com.example.app/data/edit",
            data=json.dumps({"path": "files/notes.txt", "content": "hi", "scope": "public"}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    mock_edit.assert_called_once_with("s1", "com.example.app", "files/notes.txt", "hi", "public")


def test_data_edit_shared_pref_entry_when_key_present(auth_client):
    with patch("routes.app_data.app_data.edit_shared_pref_entry", return_value={"ok": True}) as mock_edit:
        res = auth_client.post(
            "/api/devices/s1/packages/com.example.app/data/edit",
            data=json.dumps({"path": "shared_prefs/app.xml", "key": "token", "value": "new", "value_type": "string"}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    mock_edit.assert_called_once_with("s1", "com.example.app", "shared_prefs/app.xml", "token", "new", "string", "private")


def test_data_edit_requires_path(auth_client):
    res = auth_client.post(
        "/api/devices/s1/packages/com.example.app/data/edit",
        data=json.dumps({"content": "hi"}),
        content_type="application/json",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_path"


def test_data_edit_requires_content_when_not_shared_pref(auth_client):
    res = auth_client.post(
        "/api/devices/s1/packages/com.example.app/data/edit",
        data=json.dumps({"path": "files/notes.txt"}),
        content_type="application/json",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_content"


def test_data_edit_audits_on_success(auth_client):
    with patch("routes.app_data.app_data.edit_file", return_value={"ok": True}), \
         patch("routes.app_data.auth.audit_log") as mock_audit:
        auth_client.post(
            "/api/devices/s1/packages/com.example.app/data/edit",
            data=json.dumps({"path": "files/notes.txt", "content": "hi"}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    mock_audit.assert_called_once()
    assert mock_audit.call_args.args[0] == "app_data_edit"


def test_data_edit_requires_csrf(auth_client):
    res = auth_client.post(
        "/api/devices/s1/packages/com.example.app/data/edit",
        data=json.dumps({"path": "files/notes.txt", "content": "hi"}),
        content_type="application/json",
    )
    assert res.status_code == 403


def test_data_edit_requires_login(client):
    res = client.post("/api/devices/s1/packages/com.example.app/data/edit", data=json.dumps({}), content_type="application/json")
    assert res.status_code == 401


# --- POST /data/delete -----------------------------------------------------------

def test_data_delete_with_paths_list(auth_client):
    with patch("routes.app_data.app_data.delete_data", return_value={"ok": True, "results": []}) as mock_delete:
        res = auth_client.post(
            "/api/devices/s1/packages/com.example.app/data/delete",
            data=json.dumps({"paths": ["files/a.txt", "files/b.txt"], "scope": "private"}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    assert res.status_code == 200
    mock_delete.assert_called_once_with("s1", "com.example.app", ["files/a.txt", "files/b.txt"], "private")


def test_data_delete_with_single_path_shorthand(auth_client):
    with patch("routes.app_data.app_data.delete_data", return_value={"ok": True, "results": []}) as mock_delete:
        auth_client.post(
            "/api/devices/s1/packages/com.example.app/data/delete",
            data=json.dumps({"path": "files/a.txt"}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    mock_delete.assert_called_once_with("s1", "com.example.app", ["files/a.txt"], "private")


def test_data_delete_requires_paths(auth_client):
    res = auth_client.post(
        "/api/devices/s1/packages/com.example.app/data/delete",
        data=json.dumps({}),
        content_type="application/json",
        headers={"X-CSRF-Token": auth_client.csrf_token},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_paths"


def test_data_delete_audits_on_success(auth_client):
    with patch("routes.app_data.app_data.delete_data", return_value={"ok": True, "results": []}), \
         patch("routes.app_data.auth.audit_log") as mock_audit:
        auth_client.post(
            "/api/devices/s1/packages/com.example.app/data/delete",
            data=json.dumps({"paths": ["files/a.txt"]}),
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
    mock_audit.assert_called_once()
    assert mock_audit.call_args.args[0] == "app_data_delete"


def test_data_delete_requires_csrf(auth_client):
    res = auth_client.post(
        "/api/devices/s1/packages/com.example.app/data/delete",
        data=json.dumps({"paths": ["files/a.txt"]}),
        content_type="application/json",
    )
    assert res.status_code == 403


def test_data_delete_requires_login(client):
    res = client.post("/api/devices/s1/packages/com.example.app/data/delete", data=json.dumps({}), content_type="application/json")
    assert res.status_code == 401
