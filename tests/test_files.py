from unittest.mock import MagicMock, patch

import pytest

from adb import files
from adb.files import _parse_ls_line, preview_kind


def test_parse_ls_line_directory():
    entry = _parse_ls_line("drwxrwx--x 4 root sdcard_rw 4096 2026-07-06 10:00 Android")
    assert entry == {
        "name": "Android", "type": "dir", "size": 4096, "mtime": "2026-07-06 10:00",
        "perms": "drwxrwx--x", "is_symlink": False, "symlink_target": None, "parseable": True,
    }


def test_parse_ls_line_file():
    entry = _parse_ls_line("-rw-rw---- 1 root sdcard_rw 12345 2026-07-06 10:01 test.txt")
    assert entry["type"] == "file"
    assert entry["size"] == 12345
    assert entry["name"] == "test.txt"


def test_parse_ls_line_symlink_extracts_target():
    entry = _parse_ls_line("lrwxrwxrwx 1 root root 10 2026-07-06 10:02 link -> /sdcard/x")
    assert entry["type"] == "symlink"
    assert entry["is_symlink"] is True
    assert entry["name"] == "link"
    assert entry["symlink_target"] == "/sdcard/x"


def test_parse_ls_line_garbled_line_falls_back_gracefully():
    entry = _parse_ls_line("not a normal ls -la line at all")
    assert entry["parseable"] is False
    assert entry["name"] == "not a normal ls -la line at all"
    assert entry["type"] == "unknown"


def test_parse_ls_line_skips_total_and_blank_lines():
    assert _parse_ls_line("total 48") is None
    assert _parse_ls_line("   ") is None


def test_preview_kind_classification():
    assert preview_kind("/sdcard/photo.JPG") == "image"
    assert preview_kind("/sdcard/notes.txt") == "text"
    assert preview_kind("/sdcard/app.apk") == "unsupported"


def test_list_directory_success_builds_entries_and_breadcrumbs():
    stdout = (
        "total 8\n"
        "drwxrwx--x 4 root sdcard_rw 4096 2026-07-06 10:00 Android\n"
        "-rw-rw---- 1 root sdcard_rw 100 2026-07-06 10:01 a.txt\n"
    )
    with patch("adb.files.manager.validate_serial", return_value="s1"), \
         patch("adb.files.manager.shell", return_value=(stdout, "", 0)):
        result = files.list_directory("s1", "/sdcard/x/")
    assert result["ok"] is True
    assert result["path"] == "/sdcard/x"
    assert [e["name"] for e in result["entries"]] == ["Android", "a.txt"]  # dirs first
    assert result["breadcrumbs"] == [
        {"name": "/", "path": "/"}, {"name": "sdcard", "path": "/sdcard"}, {"name": "x", "path": "/sdcard/x"},
    ]
    assert result["parseable"] is True


def test_list_directory_permission_denied():
    with patch("adb.files.manager.validate_serial", return_value="s1"), \
         patch("adb.files.manager.shell", return_value=("", "Permission denied\n", 1)):
        result = files.list_directory("s1", "/data/data/pkg")
    assert result == {"ok": False, "error": "permission_denied"}


def test_list_directory_not_found():
    with patch("adb.files.manager.validate_serial", return_value="s1"), \
         patch("adb.files.manager.shell", return_value=("", "No such file or directory\n", 1)):
        result = files.list_directory("s1", "/nope")
    assert result == {"ok": False, "error": "not_found"}


def test_list_directory_unknown_error_truncates_detail():
    with patch("adb.files.manager.validate_serial", return_value="s1"), \
         patch("adb.files.manager.shell", return_value=("", "x" * 500, 1)):
        result = files.list_directory("s1", "/whatever")
    assert result["ok"] is False
    assert result["error"] == "unknown"
    assert len(result["detail"]) == 300


def test_search_path_success_and_truncation():
    with patch("adb.files.manager.shell", return_value=("/sdcard/a.txt\n/sdcard/b.txt\n", "", 0)):
        result = files.search_path("s1", "/sdcard", "txt", max_results=2)
    assert result["ok"] is True
    assert result["results"] == ["/sdcard/a.txt", "/sdcard/b.txt"]
    assert result["truncated"] is True


def test_search_path_partial_permission_errors_still_ok():
    with patch("adb.files.manager.shell", return_value=("/sdcard/a.txt\n", "", 1)):
        result = files.search_path("s1", "/sdcard", "txt")
    assert result["ok"] is True


def test_search_path_hard_failure():
    with patch("adb.files.manager.shell", return_value=("", "err", 2)):
        result = files.search_path("s1", "/sdcard", "txt")
    assert result == {"ok": False, "error": "search_failed"}


def test_mkdir_delete_move_copy_success_and_failure():
    with patch("adb.files.manager.shell", return_value=("", "", 0)):
        assert files.mkdir_path("s1", "/sdcard/new") == {"ok": True, "error": None}
    with patch("adb.files.manager.shell", return_value=("", "mkdir failed\n", 1)):
        assert files.mkdir_path("s1", "/sdcard/new") == {"ok": False, "error": "mkdir failed"}

    with patch("adb.files.manager.shell", return_value=("", "", 0)):
        assert files.delete_path("s1", "/sdcard/x", recursive=True) == {"ok": True, "error": None}

    with patch("adb.files.manager.shell", return_value=("", "", 0)) as mock_shell:
        files.delete_path("s1", "/sdcard/x", recursive=False)
    assert "-f " in mock_shell.call_args[0][1] and "-rf" not in mock_shell.call_args[0][1]

    with patch("adb.files.manager.shell", return_value=("", "", 0)):
        assert files.move_path("s1", "/a", "/b") == {"ok": True, "error": None}
    with patch("adb.files.manager.shell", return_value=("", "err", 1)):
        assert files.copy_path("s1", "/a", "/b") == {"ok": False, "error": "err"}


def test_rename_path_rejects_invalid_names():
    assert files.rename_path("s1", "/sdcard/x", "a/b") == {"ok": False, "error": "invalid_name"}
    assert files.rename_path("s1", "/sdcard/x", "..") == {"ok": False, "error": "invalid_name"}


def test_rename_path_delegates_to_move_with_sibling_dest():
    with patch("adb.files.move_path", return_value={"ok": True, "error": None}) as mock_move:
        files.rename_path("s1", "/sdcard/dir/old.txt", "new.txt")
    mock_move.assert_called_once_with("s1", "/sdcard/dir/old.txt", "/sdcard/dir/new.txt")


def test_rename_path_at_root():
    with patch("adb.files.move_path", return_value={"ok": True, "error": None}) as mock_move:
        files.rename_path("s1", "/old.txt", "new.txt")
    mock_move.assert_called_once_with("s1", "/old.txt", "/new.txt")


def test_pull_file_success(tmp_path):
    fake_proc = MagicMock(returncode=0, stderr="")
    with patch("adb.files.manager.validate_serial", return_value="s1"), \
         patch("adb.files.manager.run", return_value=fake_proc) as mock_run:
        (tmp_path / "a.txt").write_text("data")
        result = files.pull_file("s1", "/sdcard/a.txt", tmp_path)
    assert result == tmp_path / "a.txt"
    assert mock_run.call_args[0][0] == ["-s", "s1", "pull", "/sdcard/a.txt", str(tmp_path)]


def test_pull_file_raises_on_adb_failure(tmp_path):
    fake_proc = MagicMock(returncode=1, stderr="pull failed")
    with patch("adb.files.manager.validate_serial", return_value="s1"), \
         patch("adb.files.manager.run", return_value=fake_proc):
        with pytest.raises(files.manager.AdbError):
            files.pull_file("s1", "/sdcard/a.txt", tmp_path / "dest")


def test_pull_file_falls_back_to_single_candidate(tmp_path):
    (tmp_path / "actual_name.bin").write_text("data")
    fake_proc = MagicMock(returncode=0, stderr="")
    with patch("adb.files.manager.validate_serial", return_value="s1"), \
         patch("adb.files.manager.run", return_value=fake_proc):
        result = files.pull_file("s1", "/sdcard/expected_name.bin", tmp_path)
    assert result == tmp_path / "actual_name.bin"


def test_pull_file_raises_when_multiple_candidates_and_expected_missing(tmp_path):
    (tmp_path / "one.bin").write_text("a")
    (tmp_path / "two.bin").write_text("b")
    fake_proc = MagicMock(returncode=0, stderr="")
    with patch("adb.files.manager.validate_serial", return_value="s1"), \
         patch("adb.files.manager.run", return_value=fake_proc):
        with pytest.raises(files.manager.AdbError, match="not found"):
            files.pull_file("s1", "/sdcard/expected.bin", tmp_path)


def test_push_file_success_and_failure(tmp_path):
    local = tmp_path / "up.txt"
    local.write_text("hi")
    fake_proc = MagicMock(returncode=0, stderr="")
    with patch("adb.files.manager.validate_serial", return_value="s1"), \
         patch("adb.files.manager.run", return_value=fake_proc):
        result = files.push_file("s1", local, "/sdcard/dest")
    assert result == {"ok": True, "remote_path": "/sdcard/dest/up.txt"}

    fake_proc_fail = MagicMock(returncode=1, stderr="push failed")
    with patch("adb.files.manager.validate_serial", return_value="s1"), \
         patch("adb.files.manager.run", return_value=fake_proc_fail):
        result = files.push_file("s1", local, "/sdcard/dest")
    assert result == {"ok": False, "error": "push failed"}


def test_read_text_preview_success_and_truncation():
    with patch("adb.files.manager.shell", return_value=("hello", "", 0)):
        result = files.read_text_preview("s1", "/sdcard/a.txt", max_bytes=100)
    assert result == {"ok": True, "content": "hello", "truncated": False}

    with patch("adb.files.manager.shell", return_value=("x" * 10, "", 0)):
        result = files.read_text_preview("s1", "/sdcard/a.txt", max_bytes=10)
    assert result["truncated"] is True


def test_read_text_preview_failure():
    with patch("adb.files.manager.shell", return_value=("", "no such file", 1)):
        result = files.read_text_preview("s1", "/sdcard/missing.txt")
    assert result == {"ok": False, "error": "no such file"}


def test_zip_folder_creates_archive(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "file.txt").write_text("content")
    zip_base = tmp_path / "out"
    archive = files.zip_folder(src, zip_base)
    assert archive.exists()
    assert archive.suffix == ".zip"
