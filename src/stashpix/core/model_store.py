"""Lazy download / resolve of optional AI model checkpoints.

Models live under ``~/.stashpix/models/`` (override with ``STASHPIX_HOME``).
Per-model path overrides: ``STASHPIX_SYNCSEAL``, ``STASHPIX_WAM``.
WAM inference code (MIT) can be shallow-cloned into ``~/.stashpix/vendor/``.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Optional

from ..paths import app_home

_log = logging.getLogger(__name__)

MODELS_DIRNAME = "models"
VENDOR_DIRNAME = "vendor"

SYNCSEAL_FILENAME = "syncmodel.jit.pt"
SYNCSEAL_URL = "https://dl.fbaipublicfiles.com/wmar/syncseal/paper/syncmodel.jit.pt"

WAM_FILENAME = "wam_mit.pth"
WAM_URL = "https://dl.fbaipublicfiles.com/watermark_anything/wam_mit.pth"
WAM_PARAMS_FILENAME = "params.json"
WAM_PARAMS_URL = (
    "https://raw.githubusercontent.com/facebookresearch/watermark-anything/"
    "main/checkpoints/params.json"
)
WAM_REPO_URL = "https://github.com/facebookresearch/watermark-anything.git"
WAM_VENDOR_NAME = "watermark-anything"


def models_dir() -> Path:
    d = app_home() / MODELS_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def vendor_dir() -> Path:
    d = app_home() / VENDOR_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _download(url: str, dest: Path, *, label: str) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    _log.info("Downloading %s -> %s", label, dest)
    try:
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(dest)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
    return dest


def resolve_syncseal_path(*, download: bool = True) -> Optional[Path]:
    env = os.environ.get("STASHPIX_SYNCSEAL")
    if env:
        p = Path(env)
        return p if p.is_file() else None
    dest = models_dir() / SYNCSEAL_FILENAME
    if dest.is_file():
        return dest
    if not download:
        return None
    try:
        return _download(SYNCSEAL_URL, dest, label="SyncSeal")
    except Exception as exc:
        _log.warning("SyncSeal download failed: %s", exc)
        return None


def resolve_wam_checkpoint(*, download: bool = True) -> Optional[Path]:
    env = os.environ.get("STASHPIX_WAM")
    if env:
        p = Path(env)
        return p if p.is_file() else None
    dest = models_dir() / WAM_FILENAME
    if dest.is_file():
        return dest
    if not download:
        return None
    try:
        return _download(WAM_URL, dest, label="WAM")
    except Exception as exc:
        _log.warning("WAM checkpoint download failed: %s", exc)
        return None


def resolve_wam_params(*, download: bool = True) -> Optional[Path]:
    dest = models_dir() / WAM_PARAMS_FILENAME
    if dest.is_file():
        return dest
    if not download:
        return None
    try:
        return _download(WAM_PARAMS_URL, dest, label="WAM params.json")
    except Exception as exc:
        _log.warning("WAM params download failed: %s", exc)
        return None


def ensure_wam_repo(*, download: bool = True) -> Optional[Path]:
    """Return path to watermark-anything repo root (env override or vendor clone)."""
    env = os.environ.get("STASHPIX_WAM_ROOT")
    if env:
        p = Path(env)
        if (p / "watermark_anything").is_dir():
            return p
        return None
    root = vendor_dir() / WAM_VENDOR_NAME
    if (root / "watermark_anything").is_dir():
        return root
    if not download:
        return None
    try:
        _log.info("Cloning WAM repo (shallow) -> %s", root)
        subprocess.run(
            ["git", "clone", "--depth", "1", WAM_REPO_URL, str(root)],
            check=True,
            capture_output=True,
            text=True,
        )
        return root if (root / "watermark_anything").is_dir() else None
    except Exception as exc:
        _log.warning("WAM repo clone failed: %s", exc)
        return None


def add_wam_to_syspath(repo_root: Path) -> None:
    s = str(repo_root.resolve())
    if s not in sys.path:
        sys.path.insert(0, s)


__all__ = [
    "MODELS_DIRNAME",
    "SYNCSEAL_FILENAME",
    "SYNCSEAL_URL",
    "WAM_FILENAME",
    "WAM_URL",
    "models_dir",
    "vendor_dir",
    "resolve_syncseal_path",
    "resolve_wam_checkpoint",
    "resolve_wam_params",
    "ensure_wam_repo",
    "add_wam_to_syspath",
]
