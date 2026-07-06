import pytest

from adb import manager
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
