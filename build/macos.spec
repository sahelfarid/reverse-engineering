# PyInstaller spec -- macOS (.app bundle). Build ON macOS: pyinstaller build/macos.spec
# Produces dist/AdbDeviceManager.app. Unsigned -> Gatekeeper will warn on first
# launch (right-click > Open to bypass); signing/notarization is a stretch goal.
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
    [],
    exclude_binaries=True,
    name="AdbDeviceManager",
    debug=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="AdbDeviceManager",
)
app = BUNDLE(
    coll,
    name="AdbDeviceManager.app",
    icon=icon_path(ROOT, "app.icns"),
    bundle_identifier="dev.local.adbdevicemanager",
    info_plist={"NSHighResolutionCapable": True},
)
