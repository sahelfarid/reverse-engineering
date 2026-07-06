from unittest.mock import MagicMock, patch

import pytest

from adb import backup, manager


def test_resolve_export_path_known_and_unknown():
    assert backup.resolve_export_path("photos") == "/sdcard/DCIM"
    assert backup.resolve_export_path("not_a_target") is None


def test_dump_logcat_to_file_writes_output(tmp_path):
    fake_proc = MagicMock(stdout="logcat contents")
    with patch("adb.backup.manager.validate_serial", return_value="s1"), \
         patch("adb.backup.manager.run", return_value=fake_proc):
        out_path = backup.dump_logcat_to_file("s1", tmp_path)
    assert out_path.read_text() == "logcat contents"
    assert out_path.name == "logcat-s1.txt"


def test_dump_logcat_to_file_sanitizes_wireless_serial(tmp_path):
    fake_proc = MagicMock(stdout="x")
    with patch("adb.backup.manager.validate_serial", return_value="192.168.1.50:5555"), \
         patch("adb.backup.manager.run", return_value=fake_proc):
        out_path = backup.dump_logcat_to_file("192.168.1.50:5555", tmp_path)
    assert out_path.name == "logcat-192.168.1.50-5555.txt"


def test_export_database_rejects_unsafe_db_name():
    with patch("adb.backup.packages.validate_package", return_value="com.example.app"):
        for bad in ["../etc/passwd", "a/b", ".", ".."]:
            with pytest.raises(manager.AdbError, match="invalid database name"):
                backup.export_database("s1", "com.example.app", bad, None)


def test_export_database_uses_run_as_first(tmp_path):
    with patch("adb.backup.packages.validate_package", return_value="com.example.app"), \
         patch("adb.backup.manager.run_binary", return_value=MagicMock(returncode=0, stdout=b"db-bytes")):
        out_path = backup.export_database("s1", "com.example.app", "app.db", tmp_path)
    assert out_path.read_bytes() == b"db-bytes"


def test_export_database_falls_back_to_root(tmp_path):
    run_as_fail = MagicMock(returncode=1, stdout=b"")
    root_ok = MagicMock(returncode=0, stdout=b"root-db-bytes")
    with patch("adb.backup.packages.validate_package", return_value="com.example.app"), \
         patch("adb.backup.manager.has_root_shell", return_value=True), \
         patch("adb.backup.manager.run_binary", side_effect=[run_as_fail, root_ok]):
        out_path = backup.export_database("s1", "com.example.app", "app.db", tmp_path)
    assert out_path.read_bytes() == b"root-db-bytes"


def test_export_database_raises_when_inaccessible(tmp_path):
    run_as_fail = MagicMock(returncode=1, stdout=b"")
    with patch("adb.backup.packages.validate_package", return_value="com.example.app"), \
         patch("adb.backup.manager.has_root_shell", return_value=False), \
         patch("adb.backup.manager.run_binary", return_value=run_as_fail):
        with pytest.raises(manager.AdbError, match="not accessible"):
            backup.export_database("s1", "com.example.app", "app.db", tmp_path)


def test_export_app_data_success_via_run_as(tmp_path):
    pulled = tmp_path / "com.example.app_data.tar.gz"
    pulled.write_bytes(b"tar-bytes")
    with patch("adb.backup.packages.validate_package", return_value="com.example.app"), \
         patch("adb.backup.manager.shell", return_value=("", "", 0)) as mock_shell, \
         patch("adb.backup.adb_files.pull_file", return_value=pulled):
        result = backup.export_app_data("s1", "com.example.app", tmp_path)
    assert result == pulled
    # cleanup command should have been issued (non-root form, since run-as succeeded)
    cleanup_calls = [c for c in mock_shell.call_args_list if "rm -f" in c.args[1]]
    assert len(cleanup_calls) == 1
    assert not cleanup_calls[0].args[1].startswith("su 0")


def test_export_app_data_falls_back_to_root_tar(tmp_path):
    pulled = tmp_path / "com.example.app_data.tar.gz"
    pulled.write_bytes(b"tar-bytes")
    with patch("adb.backup.packages.validate_package", return_value="com.example.app"), \
         patch("adb.backup.manager.has_root_shell", return_value=True), \
         patch("adb.backup.manager.shell") as mock_shell, \
         patch("adb.backup.adb_files.pull_file", return_value=pulled):
        mock_shell.side_effect = [("", "run-as failed", 1), ("", "", 0), ("", "", 0)]
        result = backup.export_app_data("s1", "com.example.app", tmp_path)
    assert result == pulled
    cleanup_call = mock_shell.call_args_list[-1]
    assert cleanup_call.args[1].startswith("su 0 rm -f")


def test_export_app_data_raises_when_no_root_and_run_as_fails(tmp_path):
    with patch("adb.backup.packages.validate_package", return_value="com.example.app"), \
         patch("adb.backup.manager.has_root_shell", return_value=False), \
         patch("adb.backup.manager.shell", return_value=("", "run-as failed", 1)):
        with pytest.raises(manager.AdbError, match="not accessible"):
            backup.export_app_data("s1", "com.example.app", tmp_path)


def test_export_app_data_raises_when_root_tar_itself_fails(tmp_path):
    # This is the bug fixed in this pass: root tar's return code used to be
    # discarded, so a failing root tar fell through to pull_file() and
    # surfaced as a confusing pull error instead of a clear tar failure.
    with patch("adb.backup.packages.validate_package", return_value="com.example.app"), \
         patch("adb.backup.manager.has_root_shell", return_value=True), \
         patch("adb.backup.manager.shell") as mock_shell:
        mock_shell.side_effect = [("", "run-as failed", 1), ("", "tar: permission denied", 1)]
        with pytest.raises(manager.AdbError, match="root tar failed"):
            backup.export_app_data("s1", "com.example.app", tmp_path)
    # pull_file must never be attempted once the root tar itself failed.
    assert mock_shell.call_count == 2


def test_export_app_data_cleans_up_remote_temp_even_if_pull_fails(tmp_path):
    with patch("adb.backup.packages.validate_package", return_value="com.example.app"), \
         patch("adb.backup.manager.shell", return_value=("", "", 0)) as mock_shell, \
         patch("adb.backup.adb_files.pull_file", side_effect=manager.AdbError("pull failed")):
        with pytest.raises(manager.AdbError, match="pull failed"):
            backup.export_app_data("s1", "com.example.app", tmp_path)
    cleanup_calls = [c for c in mock_shell.call_args_list if "rm -f" in c.args[1]]
    assert len(cleanup_calls) == 1
