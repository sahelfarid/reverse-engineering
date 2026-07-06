from unittest.mock import patch

from adb import app_inspector

SAMPLE_DUMPSYS_PACKAGE = """
Packages:
  Package [com.example.app] (abcd1234):
    userId=10123
    requested permissions:
      android.permission.INTERNET
      android.permission.CAMERA
    install permissions:
      android.permission.INTERNET: granted=true
      android.permission.CAMERA: granted=false
    primaryCpuAbi=arm64-v8a
    secondaryCpuAbi=null
"""


def test_get_permissions_parses_requested_and_granted_state():
    with patch("adb.app_inspector.packages.validate_package", return_value="com.example.app"), \
         patch("adb.app_inspector.manager.shell", return_value=(SAMPLE_DUMPSYS_PACKAGE, "", 0)):
        result = app_inspector.get_permissions("s1", "com.example.app")
    assert result["requested"] == ["android.permission.CAMERA", "android.permission.INTERNET"]
    assert result["granted"] == ["android.permission.INTERNET"]
    assert result["denied"] == ["android.permission.CAMERA"]
    assert result["primary_abi"] == "arm64-v8a"


def test_get_permissions_returns_empty_on_shell_failure():
    with patch("adb.app_inspector.packages.validate_package", return_value="com.example.app"), \
         patch("adb.app_inspector.manager.shell", return_value=("", "err", 1)):
        result = app_inspector.get_permissions("s1", "com.example.app")
    assert result == {"requested": [], "granted": [], "denied": []}


SAMPLE_RESOLVER_DUMPSYS = """
Activity Resolver Table:
  Non-Data Actions:
      com.example.app/.MainActivity filter abc123

Service Resolver Table:
  Non-Data Actions:
      com.example.app/.MyService filter def456

Receiver Resolver Table:
  Non-Data Actions:
      com.example.app/.MyReceiver filter ghi789

Provider Resolver Table:
  com.example.app/.MyProvider

Other section unrelated
"""


def test_get_components_extracts_each_kind():
    with patch("adb.app_inspector.packages.validate_package", return_value="com.example.app"), \
         patch("adb.app_inspector.manager.shell", return_value=(SAMPLE_RESOLVER_DUMPSYS, "", 0)):
        result = app_inspector.get_components("s1", "com.example.app")
    assert result["activities"] == ["com.example.app/.MainActivity"]
    assert result["services"] == ["com.example.app/.MyService"]
    assert result["receivers"] == ["com.example.app/.MyReceiver"]
    assert result["providers"] == ["com.example.app/.MyProvider"]


def test_get_components_empty_on_shell_failure():
    with patch("adb.app_inspector.packages.validate_package", return_value="com.example.app"), \
         patch("adb.app_inspector.manager.shell", return_value=("", "err", 1)):
        result = app_inspector.get_components("s1", "com.example.app")
    assert result == {"activities": [], "receivers": [], "services": [], "providers": []}


def test_get_components_missing_section_is_empty_list():
    with patch("adb.app_inspector.packages.validate_package", return_value="com.example.app"), \
         patch("adb.app_inspector.manager.shell", return_value=("nothing relevant here", "", 0)):
        result = app_inspector.get_components("s1", "com.example.app")
    assert result == {"activities": [], "receivers": [], "services": [], "providers": []}


def test_get_data_dirs_accessible_via_run_as():
    with patch("adb.app_inspector.packages.validate_package", return_value="com.example.app"), \
         patch("adb.app_inspector.manager.shell") as mock_shell:
        mock_shell.side_effect = [
            ("db1.sqlite\n", "", 0),   # databases
            ("prefs.xml\n", "", 0),    # shared_prefs
            ("4.0M\t/data/data/com.example.app\n", "", 0),  # du
        ]
        result = app_inspector.get_data_dirs("s1", "com.example.app")
    assert result["accessible"] is True
    assert result["databases"] == ["db1.sqlite"]
    assert result["shared_prefs"] == ["prefs.xml"]
    assert result["size"] == "4.0M"
    assert result["limitation"] is None


def test_get_data_dirs_falls_back_to_root_when_run_as_fails():
    with patch("adb.app_inspector.packages.validate_package", return_value="com.example.app"), \
         patch("adb.app_inspector.manager.has_root_shell", return_value=True), \
         patch("adb.app_inspector.manager.shell") as mock_shell:
        # each of the three calls: run-as fails (rc!=0), then su -c succeeds
        mock_shell.side_effect = [
            ("", "run-as failed", 1), ("db1.sqlite\n", "", 0),
            ("", "run-as failed", 1), ("", "", 0),
            ("", "run-as failed", 1), ("2.0M\t/x\n", "", 0),
        ]
        result = app_inspector.get_data_dirs("s1", "com.example.app")
    assert result["accessible"] is True
    assert result["databases"] == ["db1.sqlite"]


def test_get_data_dirs_inaccessible_without_run_as_or_root():
    with patch("adb.app_inspector.packages.validate_package", return_value="com.example.app"), \
         patch("adb.app_inspector.manager.has_root_shell", return_value=False), \
         patch("adb.app_inspector.manager.shell", return_value=("", "run-as failed", 1)):
        result = app_inspector.get_data_dirs("s1", "com.example.app")
    assert result["accessible"] is False
    assert result["databases"] == []
    assert "not accessible" in result["limitation"]


def test_get_app_detail_composes_all_sections():
    with patch("adb.app_inspector.get_permissions", return_value={"requested": []}) as mock_perms, \
         patch("adb.app_inspector.get_components", return_value={"activities": []}) as mock_comp, \
         patch("adb.app_inspector.get_data_dirs", return_value={"accessible": False}) as mock_data:
        result = app_inspector.get_app_detail("s1", "com.example.app")
    assert result["package"] == "com.example.app"
    assert result["permissions"] == {"requested": []}
    assert result["components"] == {"activities": []}
    assert result["data"] == {"accessible": False}
    mock_perms.assert_called_once_with("s1", "com.example.app")
    mock_comp.assert_called_once_with("s1", "com.example.app")
    mock_data.assert_called_once_with("s1", "com.example.app")
