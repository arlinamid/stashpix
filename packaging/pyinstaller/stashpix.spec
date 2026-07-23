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
    "cryptography.hazmat.primitives.asymmetric.ed25519",
    "PIL", "PIL._tkinter_finder",
    "fastapi", "starlette", "pydantic", "multipart",
]
hiddenimports += collect_submodules("uvicorn")

# The optional AI helpers (SyncSeal / WAM) import torch lazily and degrade
# gracefully when it is absent — the portable/MSI is documented to ship WITHOUT
# torch or model weights. Without these excludes PyInstaller follows those
# in-function imports and sweeps the entire ML/data-science stack out of whatever
# global environment the build runs in (a ~550 MB MSI full of torch,
# transformers, spaCy, scipy, pandas, botocore, yt_dlp — none used by stashpix).
# stashpix imports none of these at module level; excluding them is safe and
# keeps the bundle to its real dependencies (Pillow, numpy, cryptography, cv2).
excludes = [
    # optional AI (install torch yourself to enable SyncSeal/WAM)
    "torch", "torchvision", "torchaudio", "transformers", "tokenizers",
    "onnxruntime", "sympy", "networkx",
    # spaCy / thinc stack, pulled transitively, unused here
    "spacy", "thinc", "blis", "catalogue", "srsly", "wasabi", "preshed",
    "cymem", "murmurhash", "langcodes",
    # data-science stack, unused here
    "scipy", "sklearn", "scikit_learn", "pandas", "matplotlib", "numba", "llvmlite",
    # cloud / media / networking junk from a dirty global env
    "botocore", "boto3", "s3transfer", "grpc", "yt_dlp", "mutagen", "av",
    "imageio", "imageio_ffmpeg",
]

cli = Analysis(
    [os.path.join(SPECPATH, "stashpix_cli.py")],
    pathex=[SRC],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
gui = Analysis(
    [os.path.join(SPECPATH, "stashpix_gui.py")],
    pathex=[SRC],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
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
