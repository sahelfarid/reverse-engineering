"""Per-app deep dive: permissions, native libs, data dirs, and exported
components (parsed from the resolver tables in the global `dumpsys package`
dump, since a single-package `dumpsys package <pkg>` call doesn't reliably
enumerate activities/services/receivers/providers across Android versions).
"""
import re

from . import manager, packages

_RESOLVER_HEADERS = {
    "activities": "Activity Resolver Table:",
    "receivers": "Receiver Resolver Table:",
    "services": "Service Resolver Table:",
    "providers": "Provider Resolver Table:",
}


def get_permissions(serial: str, package: str) -> dict:
    packages.validate_package(package)
    stdout, _stderr, rc = manager.shell(serial, f"dumpsys package {manager.quote_remote(package)}", timeout=30)
    if rc != 0:
        return {"requested": [], "granted": [], "denied": []}

    requested = []
    # Trailing \n is mandatory (not \n?) on each entry so this stops cleanly
    # at the next section header (e.g. "install permissions:") instead of
    # bleeding "install"/"permissions" into the requested list -- real device
    # dumps have no blank line between the two sections.
    req_match = re.search(r"requested permissions:\n((?:\s+[\w.]+\n)+)", stdout)
    if req_match:
        requested = [l.strip() for l in req_match.group(1).splitlines() if l.strip()]

    granted, denied = [], []
    for name, state in re.findall(r"(\S[\w.]*\.\w+):\s+granted=(true|false)", stdout):
        (granted if state == "true" else denied).append(name)

    abi_primary = re.search(r"primaryCpuAbi=(\S+)", stdout)
    abi_secondary = re.search(r"secondaryCpuAbi=(\S+)", stdout)

    return {
        "requested": sorted(set(requested)),
        "granted": sorted(set(granted)),
        "denied": sorted(set(denied)),
        "primary_abi": abi_primary.group(1) if abi_primary else None,
        "secondary_abi": abi_secondary.group(1) if abi_secondary else None,
    }


def get_components(serial: str, package: str) -> dict:
    packages.validate_package(package)
    stdout, _stderr, rc = manager.shell(serial, "dumpsys package", timeout=60)
    if rc != 0:
        return {kind: [] for kind in _RESOLVER_HEADERS}

    result = {}
    for kind, header in _RESOLVER_HEADERS.items():
        start = stdout.find(header)
        if start == -1:
            result[kind] = []
            continue
        end = stdout.find("\n\n", start)
        section = stdout[start:end if end != -1 else None]
        pattern = re.compile(r"([\w.]*" + re.escape(package) + r"/\S+)")
        result[kind] = sorted(set(pattern.findall(section)))
    return result


def get_data_dirs(serial: str, package: str) -> dict:
    packages.validate_package(package)
    base = f"/data/data/{package}"
    quoted_base = manager.quote_remote(base)

    def _run_as_or_root(cmd_suffix: str) -> tuple[str, int]:
        stdout, _stderr, rc = manager.shell(serial, f"run-as {manager.quote_remote(package)} {cmd_suffix}", timeout=15)
        if rc == 0:
            return stdout, rc
        if manager.has_root_shell(serial):
            stdout, _stderr, rc = manager.shell(serial, f"su -c '{cmd_suffix}'", timeout=15)
            return stdout, rc
        return "", rc

    databases, _rc1 = _run_as_or_root(f"ls {quoted_base}/databases 2>/dev/null")
    shared_prefs, _rc2 = _run_as_or_root(f"ls {quoted_base}/shared_prefs 2>/dev/null")
    du_out, rc3 = _run_as_or_root(f"du -sh {quoted_base} 2>/dev/null")

    accessible = bool(databases.strip() or shared_prefs.strip() or du_out.strip())
    return {
        "accessible": accessible,
        "databases": [l.strip() for l in databases.splitlines() if l.strip()],
        "shared_prefs": [l.strip() for l in shared_prefs.splitlines() if l.strip()],
        "size": du_out.split()[0] if du_out.strip() else None,
        "limitation": None if accessible else (
            "App data is not accessible: requires the app to be debuggable (for run-as) or a rooted device."
        ),
    }


def get_app_detail(serial: str, package: str) -> dict:
    return {
        "package": package,
        "permissions": get_permissions(serial, package),
        "components": get_components(serial, package),
        "data": get_data_dirs(serial, package),
    }
