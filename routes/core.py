from flask import Blueprint, jsonify, render_template, request, session

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
    data.pop("password_hash", None)
    config.save_settings(data)
    auth.audit_log("settings_update", {"keys": list(data.keys())})
    settings = dict(config.load_settings())
    settings.pop("password_hash", None)
    return jsonify({"ok": True, "settings": settings})


@bp.get("/api/audit")
@auth.login_required
def get_audit_log():
    return jsonify({"ok": True, "entries": auth.read_audit_log()})
