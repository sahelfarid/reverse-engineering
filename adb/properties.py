"""Categorized `getprop` viewer."""
import re

from . import manager

_PROP_LINE_RE = re.compile(r"^\[(?P<key>[^\]]+)\]:\s*\[(?P<value>.*)\]$")

# Order matters: first matching pattern wins, so specific categories are
# listed before the broader ones they'd otherwise fall into.
_CATEGORY_RULES = [
    ("Fingerprint", re.compile(r"fingerprint")),
    ("Security patch", re.compile(r"security_patch")),
    ("Bootloader", re.compile(r"bootloader")),
    ("Kernel", re.compile(r"^ro\.kernel\.|^ro\.boot\.")),
    ("Timezone", re.compile(r"timezone")),
    ("Locale", re.compile(r"locale|language|country")),
    ("CPU", re.compile(r"^ro\.product\.cpu|cpu\.abi|dalvik\.vm\.isa")),
    ("Memory", re.compile(r"dalvik\.vm\.heap|low_ram")),
    ("Radio", re.compile(r"^gsm\.|^ro\.telephony|^ril\.")),
    ("Display", re.compile(r"^ro\.sf\.|display")),
    ("Build", re.compile(r"^ro\.build\.")),
    ("Product", re.compile(r"^ro\.product\.")),
]


def _categorize(key: str) -> str:
    for category, pattern in _CATEGORY_RULES:
        if pattern.search(key):
            return category
    return "Other"


def get_properties(serial: str) -> dict:
    manager.validate_serial(serial)
    stdout, _stderr, rc = manager.shell(serial, "getprop", timeout=15)
    if rc != 0:
        raise manager.AdbError("getprop failed")

    categories: dict[str, list[dict]] = {}
    for line in stdout.splitlines():
        match = _PROP_LINE_RE.match(line)
        if not match:
            continue
        key, value = match.group("key"), match.group("value")
        category = _categorize(key)
        categories.setdefault(category, []).append({"key": key, "value": value})

    for entries in categories.values():
        entries.sort(key=lambda e: e["key"])

    return {"categories": categories, "total": sum(len(v) for v in categories.values())}
