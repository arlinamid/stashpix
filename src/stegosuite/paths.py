"""Cross-platform application data locations.

Everything the tool persists (the registry and the reference-image index) lives
under a single per-user directory, resolved identically on Windows, Linux and
macOS:

    Windows : %USERPROFILE%\\.stego         (e.g. C:\\Users\\you\\.stego)
    Linux   : $HOME/.stego                  (e.g. /home/you/.stego)
    macOS   : $HOME/.stego                  (e.g. /Users/you/.stego)

Overrides (highest priority first):
    STEGOSUITE_REGISTRY   full path to the registry JSON file
    STEGOSUITE_HOME       the application data directory (defaults to ~/.stego)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = ".stego"
REGISTRY_FILENAME = "registry.json"
REFS_DIRNAME = "stego_refs"


def asset_path(name: str) -> Path | None:
    """Resolve a bundled asset (e.g. ``icon.ico``) in both dev and frozen builds.

    Looks in the PyInstaller extraction dir first (``sys._MEIPASS/assets``),
    then falls back to the repository ``assets/`` directory. Returns ``None``
    when the asset is not found so callers can degrade gracefully.
    """
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "assets" / name)
    candidates.append(Path(__file__).resolve().parents[2] / "assets" / name)
    for path in candidates:
        if path.is_file():
            return path
    return None


def app_home() -> Path:
    """Return (and create) the per-user application data directory."""
    env = os.environ.get("STEGOSUITE_HOME")
    home = Path(env) if env else Path.home() / APP_DIR_NAME
    home.mkdir(parents=True, exist_ok=True)
    return home


def default_registry_path() -> str:
    """Registry location: ``STEGOSUITE_REGISTRY`` override, else ``~/.stego/registry.json``."""
    env = os.environ.get("STEGOSUITE_REGISTRY")
    if env:
        return env
    return str(app_home() / REGISTRY_FILENAME)


def default_refs_dir() -> str:
    """Reference-image index directory, next to the registry file."""
    return str(Path(default_registry_path()).parent / REFS_DIRNAME)


__all__ = [
    "APP_DIR_NAME",
    "REGISTRY_FILENAME",
    "REFS_DIRNAME",
    "asset_path",
    "app_home",
    "default_registry_path",
    "default_refs_dir",
]
