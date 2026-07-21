# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: one-dir bundle with two executables.

    dist/stashpix/
      ├── stashpix.exe        (CLI, console)
      ├── stashpix-gui.exe    (desktop GUI, windowed)
      └── _internal/       (shared Python runtime + dependencies + data)

Build (from the repository root):
    pyinstaller packaging/pyinstaller/stashpix.spec --noconfirm

The build environment must have the package and its optional extras installed so
that geometry (OpenCV) and the REST API (FastAPI/uvicorn) are bundled too:
    pip install -e ".[geo,api]" pyinstaller
"""

import os

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
SRC = os.path.join(ROOT, "src")
STATIC = os.path.join(SRC, "stashpix", "api", "static")
ASSETS = os.path.join(ROOT, "assets")
ICON = os.path.join(ASSETS, "icon.ico")

datas = [(STATIC, os.path.join("stashpix", "api", "static"))]
datas += [(ASSETS, "assets")]
datas += [(os.path.join(ROOT, "LICENSE"), ".")]
datas += collect_data_files("stashpix")

hiddenimports = [
    "cv2", "reedsolo", "numpy",
    "argon2", "argon2.low_level", "cryptography", "cryptography.hazmat.primitives.ciphers.aead",
    "PIL", "PIL._tkinter_finder",
    "fastapi", "starlette", "pydantic", "multipart",
]
hiddenimports += collect_submodules("uvicorn")

cli = Analysis(
    [os.path.join(SPECPATH, "stashpix_cli.py")],
    pathex=[SRC],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
gui = Analysis(
    [os.path.join(SPECPATH, "stashpix_gui.py")],
    pathex=[SRC],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

cli_pyz = PYZ(cli.pure, cli.zipped_data)
cli_exe = EXE(
    cli_pyz, cli.scripts, [],
    exclude_binaries=True,
    name="stashpix",
    console=True,
    icon=ICON,
)

gui_pyz = PYZ(gui.pure, gui.zipped_data)
gui_exe = EXE(
    gui_pyz, gui.scripts, [],
    exclude_binaries=True,
    name="stashpix-gui",
    console=False,
    icon=ICON,
)

coll = COLLECT(
    cli_exe, cli.binaries, cli.datas,
    gui_exe, gui.binaries, gui.datas,
    strip=False,
    upx=False,
    name="stashpix",
)
