"""Runtime permission viewer + grant/revoke."""
import re

from . import app_inspector, manager, packages

_PERMISSION_RE = re.compile(r"^android\.permission\.[A-Z_]+$|^[A-Za-z][A-Za-z0-9_.]*$")

# The Android "dangerous" (runtime-requested) permission group, per the
# platform permission protection level -- shown separately from normal/signature ones.
DANGEROUS_PERMISSIONS = {
    "android.permission.READ_CALENDAR", "android.permission.WRITE_CALENDAR",
    "android.permission.CAMERA",
    "android.permission.READ_CONTACTS", "android.permission.WRITE_CONTACTS", "android.permission.GET_ACCOUNTS",
    "android.permission.ACCESS_FINE_LOCATION", "android.permission.ACCESS_COARSE_LOCATION",
    "android.permission.RECORD_AUDIO",
    "android.permission.READ_PHONE_STATE", "android.permission.CALL_PHONE",
    "android.permission.READ_CALL_LOG", "android.permission.WRITE_CALL_LOG",
    "android.permission.ADD_VOICEMAIL", "android.permission.USE_SIP",
    "android.permission.SEND_SMS", "android.permission.RECEIVE_SMS", "android.permission.READ_SMS",
    "android.permission.RECEIVE_WAP_PUSH", "android.permission.RECEIVE_MMS",
    "android.permission.READ_EXTERNAL_STORAGE", "android.permission.WRITE_EXTERNAL_STORAGE",
    "android.permission.BODY_SENSORS",
    "android.permission.ACCESS_BACKGROUND_LOCATION",
    "android.permission.POST_NOTIFICATIONS",
}


def validate_permission(permission: str) -> str:
    if not permission or not _PERMISSION_RE.match(permission):
        raise manager.AdbError(f"invalid permission name: {permission!r}")
    return permission


def get_permission_detail(serial: str, package: str) -> dict:
    packages.validate_package(package)
    perms = app_inspector.get_permissions(serial, package)
    requested = perms["requested"]
    return {
        "requested": requested,
        "granted": perms["granted"],
        "denied": perms["denied"],
        "dangerous_requested": sorted(p for p in requested if p in DANGEROUS_PERMISSIONS),
        "normal_requested": sorted(p for p in requested if p not in DANGEROUS_PERMISSIONS),
    }


def grant_permission(serial: str, package: str, permission: str) -> dict:
    packages.validate_package(package)
    validate_permission(permission)
    _stdout, stderr, rc = manager.shell(
        serial, f"pm grant {manager.quote_remote(package)} {manager.quote_remote(permission)}", timeout=15
    )
    return {"ok": rc == 0, "error": None if rc == 0 else stderr.strip()[:300]}


def revoke_permission(serial: str, package: str, permission: str) -> dict:
    packages.validate_package(package)
    validate_permission(permission)
    _stdout, stderr, rc = manager.shell(
        serial, f"pm revoke {manager.quote_remote(package)} {manager.quote_remote(permission)}", timeout=15
    )
    return {"ok": rc == 0, "error": None if rc == 0 else stderr.strip()[:300]}
