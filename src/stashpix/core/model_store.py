"""Lazy download / resolve of optional AI model checkpoints.

Models live under ``~/.stashpix/models/`` (override with ``STASHPIX_HOME``).
Per-model path overrides: ``STASHPIX_SYNCSEAL``, ``STASHPIX_WAM``.
WAM inference code (MIT) can be shallow-cloned into ``~/.stashpix/vendor/``.
"""

from __future__ import annotations

import hashlib
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
SYNCSEAL_SHA256 = "37737dd17040989479087e803b07e88a4915419c071b9a78a97cf7b0e8d78d52"

WAM_FILENAME = "wam_mit.pth"
WAM_URL = "https://dl.fbaipublicfiles.com/watermark_anything/wam_mit.pth"
WAM_SHA256 = "90ef232384e023bd63245eb0c131abd69d2afc7b8f17a71ccedceb542bf009e2"
WAM_PARAMS_FILENAME = "params.json"
WAM_PARAMS_SHA256 = "d133a504d126b56b3e980add9fc014d718e3635a0f5740d8d6dc3190007fb476"
WAM_PARAMS_URL = (
    "https://raw.githubusercontent.com/facebookresearch/watermark-anything/"
    f"{'2c08af04d037d5667c02f6ddebbda9ff04581c3e'}/checkpoints/params.json"
)
WAM_REPO_URL = "https://github.com/facebookresearch/watermark-anything.git"
# Pinned commit rather than a moving branch: this repo is added to sys.path and
# imported, so whatever lands here executes with the user's privileges.
WAM_REPO_COMMIT = "2c08af04d037d5667c02f6ddebbda9ff04581c3e"
WAM_VENDOR_NAME = "watermark-anything"

# Allow an operator to bypass pinning deliberately (e.g. to try a newer
# upstream release). Off by default; never silently skipped.
_ALLOW_UNPINNED = "STASHPIX_ALLOW_UNPINNED_MODELS"


class ModelIntegrityError(RuntimeError):
    """A downloaded artifact did not match its pinned digest."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unpinned_allowed() -> bool:
    return os.environ.get(_ALLOW_UNPINNED, "").strip().lower() in {"1", "true", "yes"}


def verify_digest(path: Path, expected: Optional[str], *, label: str) -> Path:
    """Fail closed unless ``path`` matches ``expected``.

    These files are deserialized by ``torch.load`` and imported from sys.path,
    which is arbitrary code execution. A digest check is the difference between
    trusting the publisher once and trusting every future response from the CDN.
    """
    if expected is None:
        if not _unpinned_allowed():
            raise ModelIntegrityError(
                f"{label}: no pinned digest; refusing to load. "
                f"Set {_ALLOW_UNPINNED}=1 to override."
            )
        _log.warning("%s: loading without a pinned digest (override active)", label)
        return path
    actual = _sha256_file(path)
    if actual != expected:
        raise ModelIntegrityError(
            f"{label}: SHA-256 mismatch\n  expected {expected}\n  actual   {actual}"
        )
    return path


def models_dir() -> Path:
    d = app_home() / MODELS_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def vendor_dir() -> Path:
    d = app_home() / VENDOR_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _download(url: str, dest: Path, *, label: str,
              sha256: Optional[str] = None) -> Path:
    """Download to a temp file, verify, and only then publish to ``dest``.

    Verifying before the rename means a corrupted or tampered download never
    becomes the cached artifact, so a later run cannot pick it up unchecked.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return verify_digest(dest, sha256, label=label)
    tmp = dest.with_suffix(dest.suffix + ".part")
    _log.info("Downloading %s -> %s", label, dest)
    try:
        urllib.request.urlretrieve(url, tmp)
        verify_digest(tmp, sha256, label=label)
        tmp.replace(dest)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
    return dest


def _resolve(env_var: Optional[str], filename: str, url: str, sha256: str,
             *, label: str, download: bool) -> Optional[Path]:
    """Env override, else cached file, else download -- always digest-checked.

    An integrity failure propagates: a mismatching artifact is a security event,
    not a missing optional feature, so it must not degrade into "model
    unavailable" and get silently skipped.
    """
    if env_var:
        env = os.environ.get(env_var)
        if env:
            p = Path(env)
            if not p.is_file():
                return None
            return verify_digest(p, sha256, label=f"{label} (via {env_var})")
    dest = models_dir() / filename
    if dest.is_file():
        return verify_digest(dest, sha256, label=label)
    if not download:
        return None
    try:
        return _download(url, dest, label=label, sha256=sha256)
    except ModelIntegrityError:
        raise
    except Exception as exc:
        _log.warning("%s download failed: %s", label, exc)
        return None


def resolve_syncseal_path(*, download: bool = True) -> Optional[Path]:
    return _resolve("STASHPIX_SYNCSEAL", SYNCSEAL_FILENAME, SYNCSEAL_URL,
                    SYNCSEAL_SHA256, label="SyncSeal", download=download)


def resolve_wam_checkpoint(*, download: bool = True) -> Optional[Path]:
    return _resolve("STASHPIX_WAM", WAM_FILENAME, WAM_URL, WAM_SHA256,
                    label="WAM", download=download)


def resolve_wam_params(*, download: bool = True) -> Optional[Path]:
    return _resolve(None, WAM_PARAMS_FILENAME, WAM_PARAMS_URL, WAM_PARAMS_SHA256,
                    label="WAM params.json", download=download)


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
        return _verify_repo_commit(root)
    if not download:
        return None
    try:
        _log.info("Cloning WAM repo at %s -> %s", WAM_REPO_COMMIT[:12], root)
        # Fetch exactly the pinned commit rather than whatever `main` points at
        # today. This tree is imported, so an upstream force-push or account
        # compromise would otherwise run arbitrary code here.
        subprocess.run(["git", "init", "-q", str(root)], check=True,
                       capture_output=True, text=True)
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin", WAM_REPO_URL],
                       check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(root), "fetch", "-q", "--depth", "1",
                        "origin", WAM_REPO_COMMIT],
                       check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(root), "checkout", "-q", "FETCH_HEAD"],
                       check=True, capture_output=True, text=True)
        if not (root / "watermark_anything").is_dir():
            return None
        return _verify_repo_commit(root)
    except ModelIntegrityError:
        raise
    except Exception as exc:
        _log.warning("WAM repo clone failed: %s", exc)
        return None


def _verify_repo_commit(root: Path) -> Optional[Path]:
    """Confirm the vendored tree still sits on the pinned commit."""
    try:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              check=True, capture_output=True, text=True).stdout.strip()
    except Exception as exc:
        _log.warning("Could not read WAM repo HEAD: %s", exc)
        return None if not _unpinned_allowed() else root
    if head != WAM_REPO_COMMIT:
        if _unpinned_allowed():
            _log.warning("WAM repo at %s, expected %s (override active)",
                         head[:12], WAM_REPO_COMMIT[:12])
            return root
        raise ModelIntegrityError(
            f"WAM repo is at {head}, expected {WAM_REPO_COMMIT}. "
            f"Remove {root} to re-clone, or set {_ALLOW_UNPINNED}=1 to override."
        )
    return root


def add_wam_to_syspath(repo_root: Path) -> None:
    s = str(repo_root.resolve())
    if s not in sys.path:
        sys.path.insert(0, s)


__all__ = [
    "MODELS_DIRNAME",
    "SYNCSEAL_FILENAME",
    "SYNCSEAL_URL",
    "SYNCSEAL_SHA256",
    "WAM_FILENAME",
    "WAM_URL",
    "WAM_SHA256",
    "WAM_REPO_COMMIT",
    "ModelIntegrityError",
    "verify_digest",
    "models_dir",
    "vendor_dir",
    "resolve_syncseal_path",
    "resolve_wam_checkpoint",
    "resolve_wam_params",
    "ensure_wam_repo",
    "add_wam_to_syspath",
]
