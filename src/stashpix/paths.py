"""Cross-platform application data locations.

Everything the tool persists (the registry and the reference-image index) lives
under a single per-user directory, resolved identically on Windows, Linux and
macOS:

    Windows : %USERPROFILE%\\.stashpix
    Linux   : $HOME/.stashpix
    macOS   : $HOME/.stashpix

Overrides (highest priority first):
    STASHPIX_REGISTRY   full path to the registry file
    STASHPIX_HOME       the application data directory (defaults to ~/.stashpix)

Legacy ``~/.stashpix`` is migrated once on first access when ``~/.stashpix`` does
not yet exist.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

APP_DIR_NAME = ".stashpix"
LEGACY_APP_DIR_NAME = ".stashpix"
REGISTRY_FILENAME = "registry.json"
REFS_DIRNAME = "stashpix_refs"
LEGACY_REFS_DIRNAME = "stashpix_refs"
REGISTRY_KEY_FILENAME = ".registry_key"
IDENTITY_KEY_FILENAME = ".identity_ed25519"

_log = logging.getLogger(__name__)
_migration_done = False


def asset_path(name: str) -> Path | None:
    """Resolve a bundled asset (e.g. ``icon.ico``) in both dev and frozen builds."""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "assets" / name)
    candidates.append(Path(__file__).resolve().parents[2] / "assets" / name)
    for path in candidates:
        if path.is_file():
            return path
    return None


def _migrate_legacy_home() -> None:
    """One-time copy of ``~/.stashpix`` → ``~/.stashpix`` when the new dir is absent."""
    global _migration_done
    if _migration_done or os.environ.get("STASHPIX_HOME"):
        _migration_done = True
        return
    new_home = Path.home() / APP_DIR_NAME
    legacy = Path.home() / LEGACY_APP_DIR_NAME
    if new_home.exists() or not legacy.exists():
        _migration_done = True
        return
    try:
        shutil.copytree(legacy, new_home)
        legacy_refs = legacy / LEGACY_REFS_DIRNAME
        new_refs = new_home / REFS_DIRNAME
        if legacy_refs.is_dir() and not new_refs.exists():
            shutil.copytree(legacy_refs, new_refs)
        _log.info("Migrated legacy data from %s to %s", legacy, new_home)
    except OSError as exc:
        _log.warning("Legacy migration failed (%s); using fresh home", exc)
    _migration_done = True


def app_home() -> Path:
    """Return (and create) the per-user application data directory."""
    _migrate_legacy_home()
    env = os.environ.get("STASHPIX_HOME")
    home = Path(env) if env else Path.home() / APP_DIR_NAME
    home.mkdir(parents=True, exist_ok=True)
    return home


def default_registry_path() -> str:
    """Registry location: ``STASHPIX_REGISTRY`` override, else ``~/.stashpix/registry.json``."""
    env = os.environ.get("STASHPIX_REGISTRY")
    if env:
        return env
    return str(app_home() / REGISTRY_FILENAME)


def default_refs_dir() -> str:
    """Reference-image index directory, next to the registry file."""
    return str(Path(default_registry_path()).parent / REFS_DIRNAME)


def registry_key_path() -> Path:
    """Path to the auto-generated local registry encryption key file."""
    return app_home() / REGISTRY_KEY_FILENAME


def identity_key_path() -> Path:
    """Path to the owner's Ed25519 authorship identity (wrapped at rest)."""
    return app_home() / IDENTITY_KEY_FILENAME


__all__ = [
    "APP_DIR_NAME",
    "LEGACY_APP_DIR_NAME",
    "REGISTRY_FILENAME",
    "REFS_DIRNAME",
    "REGISTRY_KEY_FILENAME",
    "IDENTITY_KEY_FILENAME",
    "asset_path",
    "app_home",
    "default_registry_path",
    "default_refs_dir",
    "registry_key_path",
    "identity_key_path",
]
