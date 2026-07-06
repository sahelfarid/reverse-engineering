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
