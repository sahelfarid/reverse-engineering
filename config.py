import json
import os
import platform
import secrets
import sys
from pathlib import Path

APP_NAME = "AdbDeviceManager"


def is_frozen() -> bool:
    """True when running from a PyInstaller (or similar) frozen bundle."""
    return getattr(sys, "frozen", False)


def bundle_dir() -> Path:
    """Directory holding read-only bundled assets (templates/, static/).

    Under PyInstaller, assets added as `datas` live in the extraction dir
    exposed as sys._MEIPASS (onefile) or next to the executable (onedir).
    In a normal checkout they sit beside this file.
    """
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def user_data_dir() -> Path:
    """Per-user, writable location for state that must survive across runs.

    A frozen onefile build wipes its extraction dir between launches, so
    writable state (generated password, settings, known devices, macros,
    downloaded platform-tools/apktool/frida-server) must NOT live there.
    """
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / "adb-device-manager"


BUNDLE_DIR = bundle_dir()
TEMPLATE_DIR = BUNDLE_DIR / "templates"
STATIC_DIR = BUNDLE_DIR / "static"

# Writable root: the repo dir in a normal checkout (unchanged behaviour), a
# per-user app-data dir when frozen so state persists across runs/updates.
BASE_DIR = user_data_dir() if is_frozen() else BUNDLE_DIR
VENDOR_DIR = BASE_DIR / "vendor"
TEMP_DIR = BASE_DIR / "temp"
DATA_DIR = BASE_DIR / "data"

for _d in (VENDOR_DIR, TEMP_DIR, DATA_DIR):
    _d.mkdir(parents=True, exist_ok=True)

SETTINGS_PATH = DATA_DIR / "settings.json"
KNOWN_DEVICES_PATH = DATA_DIR / "known_devices.json"
AUDIT_LOG_PATH = DATA_DIR / "audit.log"
MACROS_PATH = DATA_DIR / "macros.json"

PLATFORM_TOOLS_URL_TEMPLATE = "https://dl.google.com/android/repo/platform-tools-latest-{tag}.zip"

DEFAULT_SETTINGS = {
    "adb_path_override": None,
    "refresh_interval_ms": 4000,
    "default_device_serial": None,
    "shell_timeout_sec": 20,
    "max_log_lines": 5000,
    "max_upload_mb": 200,
    "download_dir": str(BASE_DIR / "downloads"),
    "theme": "dark",
    "password_hash": None,
    # True once the first-launch setup screen has been completed (whether or
    # not a password was actually set) -- distinct from password_hash so a
    # user who deliberately skips setting a password isn't shown that screen
    # again on every restart.
    "auth_setup_complete": False,
}


def get_platform_tag() -> str:
    system = platform.system().lower()
    if system.startswith("win"):
        return "windows"
    if system == "darwin":
        return "darwin"
    return "linux"


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    settings.update(_load_json(SETTINGS_PATH, {}))
    if not SETTINGS_PATH.exists():
        _save_json(SETTINGS_PATH, settings)
    return settings


def save_settings(settings: dict) -> None:
    merged = load_settings()
    merged.update(settings)
    _save_json(SETTINGS_PATH, merged)


def _is_int_in_range(low: int, high: int):
    def check(value) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high
    return check


def _is_optional_str(value) -> bool:
    return value is None or isinstance(value, str)


SETTINGS_VALIDATORS = {
    "adb_path_override": _is_optional_str,
    "refresh_interval_ms": _is_int_in_range(250, 60_000),
    "default_device_serial": _is_optional_str,
    "shell_timeout_sec": _is_int_in_range(1, 300),
    "max_log_lines": _is_int_in_range(100, 200_000),
    "max_upload_mb": _is_int_in_range(1, 4096),
    "download_dir": lambda value: isinstance(value, str) and bool(value.strip()),
    "theme": lambda value: value in ("dark", "light"),
}


def validate_settings_patch(data: dict) -> tuple[dict, list[str]]:
    """Split an incoming settings patch into accepted and rejected keys.

    `password_hash` and `auth_setup_complete` are never accepted here -- they
    are only ever set by the auth setup/change-password/reset flows. Unknown
    keys and out-of-schema/out-of-range values are rejected rather than
    raising, so one bad field doesn't block the rest of a settings save.
    """
    accepted = {}
    rejected = []
    for key, value in data.items():
        validator = SETTINGS_VALIDATORS.get(key)
        if key in ("password_hash", "auth_setup_complete") or validator is None or not validator(value):
            rejected.append(key)
            continue
        accepted[key] = value
    return accepted, rejected


def load_known_devices() -> dict:
    return _load_json(KNOWN_DEVICES_PATH, {})


def save_known_devices(data: dict) -> None:
    _save_json(KNOWN_DEVICES_PATH, data)


def load_macros() -> dict:
    return _load_json(MACROS_PATH, {})


def save_macros(data: dict) -> None:
    _save_json(MACROS_PATH, data)


def generate_secret_key() -> str:
    key_path = DATA_DIR / "secret_key"
    if key_path.exists():
        return key_path.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    key_path.write_text(key, encoding="utf-8")
    return key


def regenerate_secret_key() -> str:
    """Force a fresh session-signing key, invalidating every outstanding
    session/remember-me cookie everywhere (not just the caller's browser),
    since Flask's cookie-based sessions are only as valid as their signature.
    Used by the password-reset flow."""
    key_path = DATA_DIR / "secret_key"
    key = secrets.token_hex(32)
    key_path.write_text(key, encoding="utf-8")
    return key
