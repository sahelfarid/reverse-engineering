from unittest.mock import patch

import pytest

from adb import manager
from adb.properties import _categorize, get_properties


def test_categorize_specific_before_general():
    assert _categorize("ro.build.fingerprint") == "Fingerprint"
    assert _categorize("ro.build.version.security_patch") == "Security patch"
    assert _categorize("ro.bootloader") == "Bootloader"
    assert _categorize("ro.boot.hardware") == "Kernel"
    assert _categorize("persist.sys.timezone") == "Timezone"
    assert _categorize("persist.sys.locale") == "Locale"
    assert _categorize("ro.product.cpu.abi") == "CPU"
    assert _categorize("dalvik.vm.heapsize") == "Memory"
    assert _categorize("gsm.version.baseband") == "Radio"
    assert _categorize("ro.sf.lcd_density") == "Display"
    assert _categorize("ro.build.version.sdk") == "Build"
    assert _categorize("ro.product.model") == "Product"
    assert _categorize("totally.unrelated.key") == "Other"


def test_get_properties_parses_bracketed_lines():
    sample = "[ro.product.model]: [Pixel 5]\n[ro.build.version.sdk]: [33]\n"
    with patch("adb.properties.manager.shell", return_value=(sample, "", 0)):
        result = get_properties("emulator-5554")
    assert result["total"] == 2
    product_keys = {e["key"] for e in result["categories"]["Product"]}
    assert "ro.product.model" in product_keys


def test_get_properties_skips_unbracketed_lines():
    sample = "[ro.product.model]: [Pixel 5]\nsome unrelated non-bracketed line\n"
    with patch("adb.properties.manager.shell", return_value=(sample, "", 0)):
        result = get_properties("emulator-5554")
    assert result["total"] == 1


def test_get_properties_raises_on_shell_failure():
    with patch("adb.properties.manager.shell", return_value=("", "err", 1)):
        with pytest.raises(manager.AdbError, match="getprop failed"):
            get_properties("emulator-5554")


def test_get_properties_sorts_entries_within_category():
    sample = "[ro.product.model]: [Pixel 5]\n[ro.product.brand]: [google]\n"
    with patch("adb.properties.manager.shell", return_value=(sample, "", 0)):
        result = get_properties("emulator-5554")
    keys = [e["key"] for e in result["categories"]["Product"]]
    assert keys == sorted(keys)
