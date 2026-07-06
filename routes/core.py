from flask import Blueprint, jsonify, render_template, request, session
from werkzeug.security import generate_password_hash

import auth
import config
from adb import manager as adb_manager

bp = Blueprint("core", __name__)


@bp.get("/")
def index():
    if not auth.is_setup_complete():
        return render_template("setup.html")
    if not auth.is_authenticated():
        return render_template("login.html")
    return render_template(
        "dashboard.html",
        csrf_token=auth.ensure_csrf_token(),
        settings=config.load_settings(),
    )


@bp.post("/api/auth/setup")
def setup():
    """First-launch only: optionally set a password, or explicitly skip
    (open access, matching a deliberately optional password). Rejected once
    setup has already been completed, so this can't be replayed as a bypass."""
    if auth.is_setup_complete():
        return jsonify({"ok": False, "error": "already_configured"}), 400
    data = request.get_json(silent=True) or {}
    password = (data.get("password") or "").strip() or None
    remember = bool(data.get("remember"))
    if password and len(password) < 6:
        return jsonify({"ok": False, "error": "password_too_short"}), 400
    auth.complete_setup(password, remember=remember)
    auth.audit_log("auth_setup_complete", {"password_set": bool(password)})
    return jsonify({"ok": True, "csrf_token": session.get("csrf_token", "")})


@bp.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    if not auth.verify_password(password):
        return jsonify({"ok": False, "error": "invalid_password"}), 401
    auth.login_session(remember=bool(data.get("remember")))
    return jsonify({"ok": True, "csrf_token": session["csrf_token"]})


@bp.post("/api/auth/reset")
def reset_password():
    """Forgot-password recovery. Intentionally reachable without a session or
    CSRF token -- that's the whole point of a reset -- so it relies instead
    on requiring the exact JSON confirmation flag the login page only sends
    after the user accepts an explicit confirm() dialog, plus the fact that a
    JSON POST from another origin can't reach this without a CORS preflight
    this app never grants."""
    data = request.get_json(silent=True) or {}
    if data.get("confirm") is not True:
        return jsonify({"ok": False, "error": "confirmation_required"}), 400
    auth.reset_password()
    auth.audit_log("auth_password_reset", {})
    return jsonify({"ok": True})


@bp.post("/api/auth/logout")
@auth.login_required
def logout():
    auth.logout_session()
    return jsonify({"ok": True})


@bp.post("/api/auth/change-password")
@auth.login_required
@auth.csrf_protect
def change_password():
    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")
    # No current password to check if one was never set (setup was skipped) --
    # this is how an open-access install can add a password later from Settings.
    if auth.has_password() and not auth.verify_password(current_password):
        return jsonify({"ok": False, "error": "invalid_current_password"}), 401
    if len(new_password) < 6:
        return jsonify({"ok": False, "error": "new_password_too_short"}), 400
    settings = config.load_settings()
    settings["password_hash"] = generate_password_hash(new_password)
    settings["auth_setup_complete"] = True
    config.save_settings(settings)
    auth.audit_log("password_changed", {})
    # Re-establish the session under the new password so a previously
    # open-access (no-password) caller isn't locked out by their own change;
    # preserves whatever "remember me" state the session already had.
    auth.login_session(remember=bool(session.permanent))
    return jsonify({"ok": True})


@bp.get("/api/adb/status")
def adb_status():
    return jsonify(adb_manager.get_adb_status())


@bp.post("/api/adb/install")
@auth.login_required
@auth.csrf_protect
def adb_install():
    try:
        status = adb_manager.install_adb()
    except adb_manager.AdbInstallError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    auth.audit_log("adb_install", {"path": status.get("path")})
    return jsonify({"ok": True, "status": status})


@bp.get("/api/settings")
@auth.login_required
def get_settings():
    settings = dict(config.load_settings())
    settings.pop("password_hash", None)
    return jsonify({"ok": True, "settings": settings})


@bp.post("/api/settings")
@auth.login_required
@auth.csrf_protect
def update_settings():
    data = request.get_json(silent=True) or {}
    accepted, rejected = config.validate_settings_patch(data)
    config.save_settings(accepted)
    auth.audit_log("settings_update", {"keys": list(accepted.keys()), "rejected": rejected})
    settings = dict(config.load_settings())
    settings.pop("password_hash", None)
    response = {"ok": True, "settings": settings}
    if rejected:
        response["rejected"] = rejected
    return jsonify(response)


@bp.get("/api/audit")
@auth.login_required
def get_audit_log():
    return jsonify({"ok": True, "entries": auth.read_audit_log()})
