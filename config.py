import json
import platform
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
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
