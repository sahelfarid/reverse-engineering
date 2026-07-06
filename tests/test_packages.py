from unittest.mock import MagicMock, patch

import pytest

from adb import manager, packages
from adb.packages import _parse_dumpsys_packages, validate_package

SAMPLE_DUMPSYS = """
  Package [com.example.app] (abcd1234):
    userId=10123
    codePath=/data/app/~~hash==/com.example.app-abc==
    versionCode=42 minSdk=21 targetSdk=33
    versionName=1.2.3
    firstInstallTime=2026-01-01 10:00:00
    lastUpdateTime=2026-06-01 10:00:00
    pkgFlags=[ SYSTEM HAS_CODE ]

  Package [com.example.other] (efgh5678):
    codePath=/data/app/~~hash2==/com.example.other-def==
    versionCode=7
    versionName=2.0
    firstInstallTime=2026-02-01 10:00:00
    lastUpdateTime=2026-02-01 10:00:00
    pkgFlags=[ HAS_CODE ]
"""


def test_parse_dumpsys_packages_extracts_both_entries():
    parsed = _parse_dumpsys_packages(SAMPLE_DUMPSYS)
    assert set(parsed) == {"com.example.app", "com.example.other"}
    assert parsed["com.example.app"]["version_name"] == "1.2.3"
    assert parsed["com.example.app"]["version_code"] == "42"
    assert parsed["com.example.app"]["is_system"] is True
    assert parsed["com.example.other"]["is_system"] is False
    assert parsed["com.example.other"]["version_name"] == "2.0"


def test_parse_dumpsys_packages_empty_input():
    assert _parse_dumpsys_packages("no packages here") == {}


def test_validate_package_accepts_normal_names():
    assert validate_package("com.example.app") == "com.example.app"


def test_validate_package_rejects_shell_metacharacters():
    for bad in ["com.example; rm -rf /", "", "../../etc/passwd", "com.example`whoami`"]:
        with pytest.raises(manager.AdbError):
            validate_package(bad)


def test_list_packages_uses_dumpsys_when_parseable():
    with patch("adb.packages.manager.shell", return_value=(SAMPLE_DUMPSYS, "", 0)):
        result = packages.list_packages("s1")
    assert [p["package"] for p in result] == ["com.example.app", "com.example.other"]


def test_list_packages_falls_back_to_pm_list_when_dumpsys_unparseable():
    pm_output = "package:/system/app/Foo.apk=com.example.foo\npackage:/data/app/Bar.apk=com.example.bar\n"
    with patch("adb.packages.manager.shell") as mock_shell:
        mock_shell.side_effect = [("no packages here", "", 0), (pm_output, "", 0)]
        result = packages.list_packages("s1")
    assert {p["package"] for p in result} == {"com.example.foo", "com.example.bar"}
    foo = next(p for p in result if p["package"] == "com.example.foo")
    assert foo["is_system"] is True


def test_list_packages_raises_when_dumpsys_fails():
    with patch("adb.packages.manager.shell", return_value=("", "err", 1)):
        with pytest.raises(manager.AdbError):
            packages.list_packages("s1")


def test_get_apk_path_success_and_not_found():
    with patch("adb.packages.manager.shell", return_value=("package:/data/app/x.apk\n", "", 0)):
        assert packages.get_apk_path("s1", "com.example.app") == "/data/app/x.apk"
    with patch("adb.packages.manager.shell", return_value=("", "not found", 1)):
        assert packages.get_apk_path("s1", "com.example.app") is None


def test_get_apk_size_success_and_failure():
    with patch("adb.packages.manager.shell", return_value=("12345\n", "", 0)):
        assert packages.get_apk_size("s1", "/data/app/x.apk") == 12345
    with patch("adb.packages.manager.shell", return_value=("", "err", 1)):
        assert packages.get_apk_size("s1", "/data/app/x.apk") is None


def test_install_apk_success_and_failure():
    with patch("adb.packages.manager.run", return_value=MagicMock(returncode=0, stdout="Success\n", stderr="")):
        result = packages.install_apk("s1", packages.Path("/tmp/app.apk"))
    assert result["ok"] is True
    with patch("adb.packages.manager.run", return_value=MagicMock(returncode=1, stdout="", stderr="Failure [INSTALL_FAILED]")):
        result = packages.install_apk("s1", packages.Path("/tmp/app.apk"))
    assert result["ok"] is False


def test_install_multiple_apks_builds_argv():
    with patch("adb.packages.manager.run", return_value=MagicMock(returncode=0, stdout="Success\n", stderr="")) as mock_run:
        packages.install_multiple_apks("s1", [packages.Path("/tmp/a.apk"), packages.Path("/tmp/b.apk")])
    args = mock_run.call_args[0][0]
    assert args == ["-s", "s1", "install-multiple", "-r", "/tmp/a.apk", "/tmp/b.apk"]


def test_uninstall_apk_keep_data_flag():
    with patch("adb.packages.manager.run", return_value=MagicMock(returncode=0, stdout="Success\n", stderr="")) as mock_run:
        packages.uninstall_apk("s1", "com.example.app", keep_data=True)
    assert mock_run.call_args[0][0] == ["-s", "s1", "uninstall", "-k", "com.example.app"]


def test_pm_action_functions_build_expected_commands():
    with patch("adb.packages.manager.shell", return_value=("", "", 0)) as mock_shell:
        packages.disable_package("s1", "com.example.app")
    assert "disable-user --user 0" in mock_shell.call_args[0][1]

    with patch("adb.packages.manager.shell", return_value=("", "", 0)) as mock_shell:
        packages.enable_package("s1", "com.example.app")
    assert "enable" in mock_shell.call_args[0][1]

    with patch("adb.packages.manager.shell", return_value=("", "", 0)) as mock_shell:
        packages.clear_data("s1", "com.example.app")
    assert "clear" in mock_shell.call_args[0][1]


def test_force_stop_and_launch_app():
    with patch("adb.packages.manager.shell", return_value=("", "", 0)):
        result = packages.force_stop("s1", "com.example.app")
    assert result["ok"] is True

    with patch("adb.packages.manager.shell", return_value=("", "", 0)):
        result = packages.launch_app("s1", "com.example.app")
    assert result["ok"] is True

    with patch("adb.packages.manager.shell", return_value=("no activities found", "", 0)):
        result = packages.launch_app("s1", "com.example.app")
    assert result["ok"] is False


def test_restart_app_force_stops_then_launches():
    with patch("adb.packages.force_stop", return_value={"ok": True, "output": ""}) as mock_stop, \
         patch("adb.packages.launch_app", return_value={"ok": True, "output": ""}) as mock_launch:
        packages.restart_app("s1", "com.example.app")
    mock_stop.assert_called_once_with("s1", "com.example.app")
    mock_launch.assert_called_once_with("s1", "com.example.app")


def test_pull_apk_renames_pulled_file_to_package_name(tmp_path):
    apk_path = "/data/app/x.apk"
    (tmp_path / "x.apk").write_bytes(b"apk-bytes")
    with patch("adb.packages.get_apk_path", return_value=apk_path), \
         patch("adb.packages.manager.run", return_value=MagicMock(returncode=0, stderr="")):
        result = packages.pull_apk("s1", "com.example.app", tmp_path)
    assert result == tmp_path / "com.example.app.apk"
    assert result.exists()


def test_pull_apk_raises_when_apk_path_unresolved(tmp_path):
    with patch("adb.packages.get_apk_path", return_value=None):
        with pytest.raises(manager.AdbError, match="could not resolve"):
            packages.pull_apk("s1", "com.example.app", tmp_path)


def test_pull_apk_raises_on_pull_failure(tmp_path):
    with patch("adb.packages.get_apk_path", return_value="/data/app/x.apk"), \
         patch("adb.packages.manager.run", return_value=MagicMock(returncode=1, stderr="pull failed")):
        with pytest.raises(manager.AdbError, match="pull failed"):
            packages.pull_apk("s1", "com.example.app", tmp_path)


def test_pull_apk_raises_when_pulled_file_missing(tmp_path):
    # adb reported success but the expected file never landed on disk --
    # this used to silently return a Path that doesn't exist (bug fixed in
    # this pass); now it raises instead.
    with patch("adb.packages.get_apk_path", return_value="/data/app/x.apk"), \
         patch("adb.packages.manager.run", return_value=MagicMock(returncode=0, stderr="")):
        with pytest.raises(manager.AdbError, match="not found"):
            packages.pull_apk("s1", "com.example.app", tmp_path)
