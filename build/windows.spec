# PyInstaller spec -- Windows (onefile). Build ON Windows: pyinstaller build/windows.spec
import sys
from pathlib import Path

sys.path.insert(0, str(Path(SPECPATH).resolve()))
from _common import repo_root, asset_datas, hidden_imports, icon_path

ROOT = repo_root(SPECPATH)

a = Analysis(
    [str(ROOT / "desktop.py")],
    pathex=[str(ROOT)],
    datas=asset_datas(ROOT),
    hiddenimports=hidden_imports(),
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AdbDeviceManager",
    debug=False,
    strip=False,
    upx=True,
    console=False,               # windowed GUI app, no console
    icon=icon_path(ROOT, "app.ico"),
)
