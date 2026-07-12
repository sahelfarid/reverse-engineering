"""Single-user session auth, CSRF protection, and an audit log for privileged actions.

This is a local developer tool (binds 127.0.0.1 only) but it can execute a root
shell and modify device state, so it still gets a login gate + CSRF + an audit
trail rather than being wide open.
"""
import json
import secrets
from datetime import datetime, timezone
from functools import wraps

from flask import current_app, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

import config


# TEMP DEV BYPASS: comment this back to False to restore password login.
# Keeps the local panel open while Frida/macOS tooling is being iterated.
AUTH_LOGIN_TEMP_DISABLED = True


def auth_bypass_enabled() -> bool:
    return AUTH_LOGIN_TEMP_DISABLED


def has_password() -> bool:
    if auth_bypass_enabled():
        return False
    return bool(config.load_settings().get("password_hash"))


def is_setup_complete() -> bool:
    """Whether the first-launch setup screen has been handled.

    Also true for any install that already has a password_hash from before
    this flag existed, so upgrading never re-shows the setup screen.
    """
    if auth_bypass_enabled():
        return True
    settings = config.load_settings()
    return bool(settings.get("auth_setup_complete")) or bool(settings.get("password_hash"))


def verify_password(candidate: str) -> bool:
    settings = config.load_settings()
    stored_hash = settings.get("password_hash")
    if not stored_hash:
        return False
    return check_password_hash(stored_hash, candidate)


def is_authenticated() -> bool:
    if auth_bypass_enabled():
        session["authenticated"] = True
        ensure_csrf_token()
        return True
    if is_setup_complete() and not has_password():
        return True  # password was explicitly skipped during setup -- open access by design
    return bool(session.get("authenticated"))


def login_session(remember: bool = False) -> None:
    session.permanent = remember
    session["authenticated"] = True
    session["csrf_token"] = secrets.token_hex(16)


def ensure_csrf_token() -> str:
    """Make sure the current session has a CSRF token, issuing one if not.

    Needed for the open-access (no password set) case: `login_session()` --
    which normally issues the token -- is never called there, but mutating
    routes still go through `csrf_protect`.
    """
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def complete_setup(password: str | None, remember: bool = False) -> None:
    """Handle the first-launch setup screen: optionally set a password, mark
    setup complete either way, and log the caller straight in."""
    settings = config.load_settings()
    if password:
        settings["password_hash"] = generate_password_hash(password)
    settings["auth_setup_complete"] = True
    config.save_settings(settings)
    login_session(remember=remember)


def reset_password() -> None:
    """Forgot-password recovery: clear the password and rotate the
    session-signing key, which immediately invalidates every outstanding
    session/remember-me cookie everywhere (not just the caller's browser) --
    Flask's cookie-based sessions are only as valid as their signature.
    Leaves auth_setup_complete false so the setup screen is shown again."""
    settings = config.load_settings()
    settings["password_hash"] = None
    settings["auth_setup_complete"] = False
    config.save_settings(settings)
    current_app.secret_key = config.regenerate_secret_key()
    session.clear()


def logout_session() -> None:
    session.clear()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_authenticated():
            return jsonify({"ok": False, "error": "unauthenticated"}), 401
        return view(*args, **kwargs)
    return wrapped


def csrf_protect(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if auth_bypass_enabled():
            ensure_csrf_token()
            return view(*args, **kwargs)
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            header_token = request.headers.get("X-CSRF-Token", "")
            session_token = session.get("csrf_token", "")
            if not session_token or not secrets.compare_digest(header_token, session_token):
                return jsonify({"ok": False, "error": "csrf_failed"}), 403
        return view(*args, **kwargs)
    return wrapped


def audit_log(action: str, details: dict | None = None) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "details": details or {},
        "remote_addr": request.remote_addr if request else None,
    }
    with open(config.AUDIT_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def read_audit_log(limit: int = 500) -> list[dict]:
    if not config.AUDIT_LOG_PATH.exists():
        return []
    lines = config.AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries
