import base64
import sqlite3
from unittest.mock import patch

import pytest

from adb import app_data
from adb import manager as adb_manager


# --- path/scope validation --------------------------------------------------

def test_scope_base_private_and_public():
    assert app_data._scope_base("com.example.app", "private") == "/data/data/com.example.app"
    assert app_data._scope_base("com.example.app", "public") == "/sdcard/Android/data/com.example.app"


def test_scope_base_rejects_unknown_scope():
    with pytest.raises(adb_manager.AdbError, match="invalid scope"):
        app_data._scope_base("com.example.app", "system")


def test_validate_relative_path_rejects_traversal_and_absolute():
    with pytest.raises(adb_manager.AdbError):
        app_data._validate_relative_path("../etc/passwd")
    with pytest.raises(adb_manager.AdbError):
        app_data._validate_relative_path("/etc/passwd")
    with pytest.raises(adb_manager.AdbError):
        app_data._validate_relative_path("shared_prefs/../../etc")


def test_validate_relative_path_normalizes_empty_and_dot():
    assert app_data._validate_relative_path("") == ""
    assert app_data._validate_relative_path(".") == ""
    assert app_data._validate_relative_path("shared_prefs/app.xml") == "shared_prefs/app.xml"
    assert app_data._validate_relative_path("shared_prefs/app.xml/") == "shared_prefs/app.xml"


# --- run_as_or_root ----------------------------------------------------------

def test_run_as_or_root_uses_run_as_when_it_succeeds():
    with patch("adb.app_data.manager.shell", return_value=("out", "", 0)) as mock_shell:
        stdout, rc = app_data._run_as_or_root("s1", "com.example.app", "ls /data/data/com.example.app")
    assert (stdout, rc) == ("out", 0)
    mock_shell.assert_called_once_with("s1", "run-as com.example.app ls /data/data/com.example.app", timeout=15)


def test_run_as_or_root_falls_back_to_su_when_rooted():
    with patch("adb.app_data.manager.shell", side_effect=[("", "run-as: not debuggable", 1), ("out", "", 0)]) as mock_shell, \
         patch("adb.app_data.manager.has_root_shell", return_value=True):
        stdout, rc = app_data._run_as_or_root("s1", "com.example.app", "ls /data/data/com.example.app")
    assert (stdout, rc) == ("out", 0)
    assert mock_shell.call_args_list[1].args[1] == "su -c 'ls /data/data/com.example.app'"


def test_run_as_or_root_quotes_su_argument_safely_when_cmd_has_quotes():
    # cmd_suffix already contains single-quoted fragments (as manager.quote_remote
    # would produce for a path with a space) -- the su fallback must re-quote
    # the WHOLE string as one opaque argument, not nest raw quotes.
    cmd = "ls '/data/data/com.example.app/a b' 2>/dev/null"
    with patch("adb.app_data.manager.shell", side_effect=[("", "", 1), ("out", "", 0)]) as mock_shell, \
         patch("adb.app_data.manager.has_root_shell", return_value=True):
        app_data._run_as_or_root("s1", "com.example.app", cmd)
    su_arg = mock_shell.call_args_list[1].args[1]
    assert su_arg.startswith("su -c ")
    # Must not just be `su -c '<cmd verbatim>'` (that would break on the inner quotes).
    assert su_arg != f"su -c '{cmd}'"


def test_run_as_or_root_returns_empty_when_no_root_available():
    with patch("adb.app_data.manager.shell", return_value=("", "run-as: not debuggable", 1)), \
         patch("adb.app_data.manager.has_root_shell", return_value=False):
        stdout, rc = app_data._run_as_or_root("s1", "com.example.app", "ls x")
    assert (stdout, rc) == ("", 1)


# --- list_data / get_data_overview -------------------------------------------

_LS_SAMPLE = (
    "drwxrwx--x 2 u0_a123 u0_a123 4096 2024-01-01 00:00 databases\n"
    "drwxrwx--x 2 u0_a123 u0_a123 4096 2024-01-01 00:00 shared_prefs\n"
    "-rw-rw---- 1 u0_a123 u0_a123   10 2024-01-01 00:00 cookie.db\n"
)


def test_list_data_private_success():
    with patch("adb.app_data._run_as_or_root", return_value=(_LS_SAMPLE, 0)):
        result = app_data.list_data("s1", "com.example.app", scope="private", path="")
    assert result["ok"] is True
    assert result["accessible"] is True
    names = [e["name"] for e in result["entries"]]
    assert "databases" in names and "shared_prefs" in names


def test_list_data_private_inaccessible_reports_limitation():
    with patch("adb.app_data._run_as_or_root", return_value=("", 1)):
        result = app_data.list_data("s1", "com.example.app", scope="private")
    assert result["ok"] is False
    assert result["accessible"] is False
    assert "run-as" in result["limitation"]


def test_list_data_public_uses_plain_shell_no_run_as():
    with patch("adb.app_data.manager.shell", return_value=(_LS_SAMPLE, "", 0)) as mock_shell:
        result = app_data.list_data("s1", "com.example.app", scope="public")
    assert result["ok"] is True
    assert mock_shell.call_args.args[0] == "s1"
    assert "/sdcard/Android/data/com.example.app" in mock_shell.call_args.args[1]


def test_list_data_rejects_traversal_path():
    with pytest.raises(adb_manager.AdbError):
        app_data.list_data("s1", "com.example.app", scope="private", path="../../etc")


def test_get_data_overview_combines_both_scopes():
    with patch("adb.app_data.list_data", side_effect=[
        {"ok": True, "scope": "private", "accessible": True, "entries": []},
        {"ok": False, "scope": "public", "accessible": False, "entries": []},
    ]) as mock_list:
        result = app_data.get_data_overview("s1", "com.example.app")
    assert result["package"] == "com.example.app"
    assert result["private"]["ok"] is True
    assert result["public"]["ok"] is False
    assert mock_list.call_args_list[0].kwargs == {"scope": "private", "path": ""}
    assert mock_list.call_args_list[1].kwargs == {"scope": "public", "path": ""}


# --- read_data_file ------------------------------------------------------------

def test_read_data_file_requires_path():
    with pytest.raises(adb_manager.AdbError, match="missing path"):
        app_data.read_data_file("s1", "com.example.app", "")


def test_read_data_file_database_short_circuits_without_reading_bytes():
    with patch("adb.app_data._read_bytes") as mock_read:
        result = app_data.read_data_file("s1", "com.example.app", "databases/cookie.db")
    assert result["kind"] == "database"
    mock_read.assert_not_called()


def test_read_data_file_reports_inaccessible():
    with patch("adb.app_data._read_bytes", return_value=None):
        result = app_data.read_data_file("s1", "com.example.app", "files/notes.txt")
    assert result == {"ok": False, "error": "read_failed_or_inaccessible", "path": "files/notes.txt", "scope": "private"}


def test_read_data_file_plain_text():
    with patch("adb.app_data._read_bytes", return_value=b"hello world"):
        result = app_data.read_data_file("s1", "com.example.app", "files/notes.txt")
    assert result["ok"] is True
    assert result["kind"] == "text"
    assert result["content"] == "hello world"
    assert result["truncated"] is False


def test_read_data_file_parses_shared_prefs_xml():
    xml = (
        "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n"
        "<map><string name=\"token\">abc123</string>"
        "<boolean name=\"onboarded\" value=\"true\" />"
        "<int name=\"launches\" value=\"7\" /></map>"
    )
    with patch("adb.app_data._read_bytes", return_value=xml.encode("utf-8")):
        result = app_data.read_data_file("s1", "com.example.app", "shared_prefs/app.xml")
    assert result["kind"] == "shared_prefs"
    parsed = {e["key"]: e["value"] for e in result["parsed"]}
    assert parsed["token"] == "abc123"
    assert parsed["onboarded"] == "true"
    assert parsed["launches"] == "7"


def test_read_data_file_parses_json():
    with patch("adb.app_data._read_bytes", return_value=b'{"a": 1}'):
        result = app_data.read_data_file("s1", "com.example.app", "files/config.json")
    assert result["kind"] == "json"
    assert result["parsed"] == {"a": 1}


def test_read_data_file_binary_returns_base64():
    raw = b"\x00\x01\x02binarydata"
    with patch("adb.app_data._read_bytes", return_value=raw):
        result = app_data.read_data_file("s1", "com.example.app", "files/blob.bin")
    assert result["kind"] == "binary"
    assert base64.b64decode(result["base64"]) == raw


# --- write path ---------------------------------------------------------------

def test_write_bytes_rejects_oversized_content():
    ok, error = app_data._write_bytes("s1", "com.example.app", "private", "/data/data/com.example.app/x", b"x" * (app_data._MAX_EDIT_BYTES + 1))
    assert ok is False
    assert "too large" in error


def test_edit_file_writes_and_returns_ok():
    with patch("adb.app_data._write_bytes", return_value=(True, None)) as mock_write:
        result = app_data.edit_file("s1", "com.example.app", "files/notes.txt", "new content")
    assert result == {"ok": True, "path": "files/notes.txt", "scope": "private"}
    assert mock_write.call_args.args[4] == b"new content"


def test_edit_file_raises_on_write_failure():
    with patch("adb.app_data._write_bytes", return_value=(False, "write_failed")):
        with pytest.raises(adb_manager.AdbError, match="write_failed"):
            app_data.edit_file("s1", "com.example.app", "files/notes.txt", "x")


def test_edit_shared_pref_entry_updates_existing_key():
    xml = "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n<map><string name=\"token\">old</string></map>"
    with patch("adb.app_data.read_data_file", return_value={"ok": True, "content": xml}), \
         patch("adb.app_data._write_bytes", return_value=(True, None)) as mock_write:
        result = app_data.edit_shared_pref_entry("s1", "com.example.app", "shared_prefs/app.xml", "token", "new", "string")
    assert result == {"ok": True, "path": "shared_prefs/app.xml", "scope": "private", "key": "token"}
    written = mock_write.call_args.args[4]
    root_text = written.decode("utf-8")
    assert "<string name=\"token\">new</string>" in root_text
    assert "old" not in root_text


def test_edit_shared_pref_entry_rejects_unsupported_type():
    with pytest.raises(adb_manager.AdbError, match="unsupported"):
        app_data.edit_shared_pref_entry("s1", "com.example.app", "shared_prefs/app.xml", "k", "v", "double")


def test_edit_shared_pref_entry_requires_key():
    with pytest.raises(adb_manager.AdbError, match="missing key"):
        app_data.edit_shared_pref_entry("s1", "com.example.app", "shared_prefs/app.xml", "", "v")


def test_edit_shared_pref_entry_rejects_non_map_root():
    with patch("adb.app_data.read_data_file", return_value={"ok": True, "content": "<root></root>"}):
        with pytest.raises(adb_manager.AdbError, match="not a SharedPreferences"):
            app_data.edit_shared_pref_entry("s1", "com.example.app", "shared_prefs/app.xml", "k", "v")


def test_edit_shared_pref_entry_propagates_read_failure():
    with patch("adb.app_data.read_data_file", return_value={"ok": False, "error": "read_failed_or_inaccessible"}):
        with pytest.raises(adb_manager.AdbError, match="read_failed_or_inaccessible"):
            app_data.edit_shared_pref_entry("s1", "com.example.app", "shared_prefs/app.xml", "k", "v")


# --- delete_data ----------------------------------------------------------------

def test_delete_data_requires_paths():
    with pytest.raises(adb_manager.AdbError, match="no paths"):
        app_data.delete_data("s1", "com.example.app", [])


def test_delete_data_refuses_to_delete_scope_root():
    result = app_data.delete_data("s1", "com.example.app", ["", ".", "../escape"])
    assert result["ok"] is False
    assert all(r["ok"] is False and r["error"] == "invalid_path" for r in result["results"])


def test_delete_data_runs_rm_for_each_valid_path():
    with patch("adb.app_data._run_as_or_root", return_value=("", 0)) as mock_run:
        result = app_data.delete_data("s1", "com.example.app", ["files/a.txt", "files/b.txt"])
    assert result["ok"] is True
    assert len(result["results"]) == 2
    assert mock_run.call_count == 2


def test_delete_data_public_scope_uses_plain_shell():
    with patch("adb.app_data.manager.shell", return_value=("", "", 0)) as mock_shell:
        result = app_data.delete_data("s1", "com.example.app", ["cache/x"], scope="public")
    assert result["ok"] is True
    mock_shell.assert_called_once()


# --- databases -------------------------------------------------------------------

def test_list_databases_inaccessible():
    with patch("adb.app_data._list_dir", return_value=(None, "not_found_or_inaccessible")):
        result = app_data.list_databases("s1", "com.example.app")
    assert result == {"ok": False, "accessible": False, "databases": [],
                       "limitation": "Private app data is not accessible: requires the app to be debuggable (for run-as) or a rooted device."}


def test_list_databases_filters_to_db_extensions():
    entries = [
        {"name": "cookies.db", "type": "file"},
        {"name": "cookies.db-journal", "type": "file"},
        {"name": "wal.sqlite", "type": "file"},
        {"name": "subdir", "type": "dir"},
    ]
    with patch("adb.app_data._list_dir", return_value=(entries, None)):
        result = app_data.list_databases("s1", "com.example.app")
    assert result["ok"] is True
    assert result["databases"] == ["cookies.db", "wal.sqlite"]


def test_query_database_rejects_invalid_name():
    with pytest.raises(adb_manager.AdbError, match="invalid database name"):
        app_data.query_database("s1", "com.example.app", "../x.db")


def test_query_database_raises_when_not_accessible():
    with patch("adb.app_data._read_bytes", return_value=None):
        with pytest.raises(adb_manager.AdbError, match="not accessible"):
            app_data.query_database("s1", "com.example.app", "cookies.db")


def _build_sqlite_bytes(tmp_path) -> bytes:
    db_path = tmp_path / "src.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO users (name) VALUES ('alice'), ('bob')")
    conn.commit()
    conn.close()
    return db_path.read_bytes()


def test_query_database_lists_tables_without_query(tmp_path):
    raw = _build_sqlite_bytes(tmp_path)
    with patch("adb.app_data._read_bytes", return_value=raw):
        result = app_data.query_database("s1", "com.example.app", "cookies.db")
    assert result["ok"] is True
    assert result["tables"] == ["users"]
    assert result["rows"] == []


def test_query_database_runs_select_query(tmp_path):
    raw = _build_sqlite_bytes(tmp_path)
    with patch("adb.app_data._read_bytes", return_value=raw):
        result = app_data.query_database("s1", "com.example.app", "cookies.db", query="SELECT * FROM users ORDER BY id")
    assert result["columns"] == ["id", "name"]
    assert result["rows"] == [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]


def test_query_database_rejects_non_select_query(tmp_path):
    raw = _build_sqlite_bytes(tmp_path)
    with patch("adb.app_data._read_bytes", return_value=raw):
        with pytest.raises(adb_manager.AdbError, match="only SELECT"):
            app_data.query_database("s1", "com.example.app", "cookies.db", query="DELETE FROM users")


def test_query_database_wraps_sql_errors(tmp_path):
    raw = _build_sqlite_bytes(tmp_path)
    with patch("adb.app_data._read_bytes", return_value=raw):
        with pytest.raises(adb_manager.AdbError, match="query failed"):
            app_data.query_database("s1", "com.example.app", "cookies.db", query="SELECT * FROM does_not_exist")
