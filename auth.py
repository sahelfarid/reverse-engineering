"""Single-user session auth, CSRF protection, and an audit log for privileged actions.

This is a local developer tool (binds 127.0.0.1 only) but it can execute a root
shell and modify device state, so it still gets a login gate + CSRF + an audit
trail rather than being wide open.
"""
import json
import secrets
from datetime import datetime, timezone
from functools import wraps

from flask import jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

import config


def ensure_password() -> str | None:
    """Generate+store a random password on first run. Returns the plaintext only when newly created."""
    settings = config.load_settings()
    if settings.get("password_hash"):
        return None
    plaintext = secrets.token_urlsafe(9)
    settings["password_hash"] = generate_password_hash(plaintext)
    config.save_settings(settings)
    return plaintext


def verify_password(candidate: str) -> bool:
    settings = config.load_settings()
    stored_hash = settings.get("password_hash")
    if not stored_hash:
        return False
    return check_password_hash(stored_hash, candidate)


def is_authenticated() -> bool:
    return bool(session.get("authenticated"))


def login_session() -> None:
    session["authenticated"] = True
    session["csrf_token"] = secrets.token_hex(16)


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
