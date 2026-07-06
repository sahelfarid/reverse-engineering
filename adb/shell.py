"""Backing logic for the web shell terminal tab."""
from . import manager


def run_command(serial: str, command: str, use_su: bool = False, timeout: int | None = None) -> dict:
    manager.validate_serial(serial)
    if not command.strip():
        return {"stdout": "", "stderr": "", "returncode": 0}
    remote_cmd = f"su -c {manager.quote_remote(command)}" if use_su else command
    stdout, stderr, rc = manager.shell(serial, remote_cmd, timeout=timeout)
    return {"stdout": stdout, "stderr": stderr, "returncode": rc}


def su_available(serial: str) -> bool:
    return manager.has_root_shell(serial)
