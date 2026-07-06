import config


# --- settings patch validation ------------------------------------------------

def test_validate_settings_patch_accepts_known_in_range_values():
    accepted, rejected = config.validate_settings_patch({
        "refresh_interval_ms": 5000,
        "shell_timeout_sec": 30,
        "max_log_lines": 10000,
        "max_upload_mb": 500,
        "theme": "light",
        "adb_path_override": None,
        "download_dir": "/tmp/downloads",
    })
    assert rejected == []
    assert accepted["refresh_interval_ms"] == 5000
    assert accepted["theme"] == "light"


def test_validate_settings_patch_rejects_password_hash():
    accepted, rejected = config.validate_settings_patch({"password_hash": "hacked"})
    assert accepted == {}
    assert rejected == ["password_hash"]


def test_validate_settings_patch_rejects_unknown_keys():
    accepted, rejected = config.validate_settings_patch({"totally_unknown_key": "x"})
    assert accepted == {}
    assert rejected == ["totally_unknown_key"]


def test_validate_settings_patch_rejects_out_of_range_values():
    accepted, rejected = config.validate_settings_patch({
        "shell_timeout_sec": 0,
        "max_upload_mb": -5,
        "refresh_interval_ms": 10,
        "theme": "solarized",
    })
    assert accepted == {}
    assert set(rejected) == {"shell_timeout_sec", "max_upload_mb", "refresh_interval_ms", "theme"}


def test_validate_settings_patch_rejects_wrong_types():
    accepted, rejected = config.validate_settings_patch({
        "shell_timeout_sec": "20",  # string, not int
        "shell_timeout_sec_bool": True,  # bool is an int subclass in Python; must not sneak through
        "max_log_lines": 500.5,
    })
    assert accepted == {}
    assert "shell_timeout_sec" in rejected
    assert "max_log_lines" in rejected


def test_validate_settings_patch_partial_success_keeps_good_keys():
    accepted, rejected = config.validate_settings_patch({
        "theme": "dark",
        "shell_timeout_sec": -1,
    })
    assert accepted == {"theme": "dark"}
    assert rejected == ["shell_timeout_sec"]


# --- settings.json corrupt-file recovery -------------------------------------

def test_load_settings_recovers_from_corrupt_json(tmp_path, monkeypatch):
    bad_path = tmp_path / "settings.json"
    bad_path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(config, "SETTINGS_PATH", bad_path)
    settings = config.load_settings()
    assert settings["theme"] == config.DEFAULT_SETTINGS["theme"]


def test_load_settings_merges_over_defaults(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text('{"theme": "light"}', encoding="utf-8")
    monkeypatch.setattr(config, "SETTINGS_PATH", path)
    settings = config.load_settings()
    assert settings["theme"] == "light"
    assert settings["shell_timeout_sec"] == config.DEFAULT_SETTINGS["shell_timeout_sec"]


# --- secret key persistence ---------------------------------------------------

def test_generate_secret_key_persists_across_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    first = config.generate_secret_key()
    second = config.generate_secret_key()
    assert first == second
    assert (tmp_path / "secret_key").read_text(encoding="utf-8").strip() == first


def test_generate_secret_key_creates_hex_token(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    key = config.generate_secret_key()
    assert len(key) == 64
    int(key, 16)  # raises ValueError if not valid hex
