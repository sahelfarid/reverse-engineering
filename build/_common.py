"""Shared helpers for the per-OS PyInstaller spec files.

Imported from each spec via `sys.path` (the spec adds its own dir). Keeps the
datas/hiddenimports/icon logic in one place instead of copy-pasting it three
times. PyInstaller cannot cross-compile, so there is still one spec per OS --
they only differ in output format (onefile exe vs .app bundle) and icon.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


def repo_root(specpath: str) -> Path:
    # build/<os>.spec -> repo root is the parent of build/.
    return Path(specpath).resolve().parent


def asset_datas(root: Path):
    """templates/ and static/ are not Python imports, so PyInstaller's scanner
    misses them -- bundle them explicitly or Flask 404s every page."""
    return [
        (str(root / "templates"), "templates"),
        (str(root / "static"), "static"),
    ]


def hidden_imports():
    # pywebview loads its OS backend lazily; pull the whole package in so the
    # frozen build doesn't miss the platform module.
    return collect_submodules("webview")


def icon_path(root: Path, filename: str):
    """Return the icon path if the placeholder was replaced with a real asset,
    else None so the build still succeeds with the default icon."""
    p = root / "build" / "icons" / filename
    return str(p) if p.exists() else None
