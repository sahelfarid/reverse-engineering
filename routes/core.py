from flask import Blueprint, jsonify, render_template, request, session
from werkzeug.security import generate_password_hash

import auth
import config
from adb import manager as adb_manager

bp = Blueprint("core", __name__)


@bp.get("/")
def index():
    if not auth.is_authenticated():
        return render_template("login.html")
    return render_template(
        "dashboard.html",
        csrf_token=session.get("csrf_token", ""),
        settings=config.load_settings(),
    )


@bp.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    if not auth.verify_password(password):
        return jsonify({"ok": False, "error": "invalid_password"}), 401
    auth.login_session()
    return jsonify({"ok": True, "csrf_token": session["csrf_token"]})


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
    if not auth.verify_password(current_password):
        return jsonify({"ok": False, "error": "invalid_current_password"}), 401
    if len(new_password) < 6:
        return jsonify({"ok": False, "error": "new_password_too_short"}), 400
    settings = config.load_settings()
    settings["password_hash"] = generate_password_hash(new_password)
    config.save_settings(settings)
    auth.audit_log("password_changed", {})
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
