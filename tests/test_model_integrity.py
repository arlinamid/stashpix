"""Pinned digests for the optional AI artifacts.

These files are fed to ``torch.load(weights_only=False)`` and the vendored repo
is put on ``sys.path`` and imported -- both are arbitrary code execution with the
user's privileges. v1.4.0 downloaded them over plain HTTPS with no integrity
check and cloned whatever ``main`` pointed at, so a CDN or upstream-account
compromise was enough to run code on every machine that enabled the feature.
"""

from __future__ import annotations

import hashlib

import pytest

from stashpix.core import model_store
from stashpix.core.model_store import (
    SYNCSEAL_SHA256,
    WAM_REPO_COMMIT,
    WAM_SHA256,
    ModelIntegrityError,
    verify_digest,
)


def _write(tmp_path, name, data: bytes):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_digests_are_pinned_and_well_formed():
    for digest in (SYNCSEAL_SHA256, WAM_SHA256):
        assert digest is not None
        assert len(digest) == 64
        int(digest, 16)          # must be valid hex


def test_repo_commit_is_a_full_sha():
    assert len(WAM_REPO_COMMIT) == 40
    int(WAM_REPO_COMMIT, 16)


def test_matching_digest_passes(tmp_path):
    data = b"model bytes"
    path = _write(tmp_path, "m.bin", data)
    assert verify_digest(path, hashlib.sha256(data).hexdigest(), label="test") == path


def test_mismatching_digest_is_rejected(tmp_path):
    path = _write(tmp_path, "m.bin", b"tampered")
    with pytest.raises(ModelIntegrityError):
        verify_digest(path, hashlib.sha256(b"original").hexdigest(), label="test")


def test_unpinned_is_refused_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("STASHPIX_ALLOW_UNPINNED_MODELS", raising=False)
    path = _write(tmp_path, "m.bin", b"whatever")
    with pytest.raises(ModelIntegrityError):
        verify_digest(path, None, label="test")


def test_unpinned_allowed_only_with_explicit_override(tmp_path, monkeypatch):
    monkeypatch.setenv("STASHPIX_ALLOW_UNPINNED_MODELS", "1")
    path = _write(tmp_path, "m.bin", b"whatever")
    assert verify_digest(path, None, label="test") == path


def test_tampered_download_never_becomes_the_cached_file(tmp_path, monkeypatch):
    """A bad download must not be left behind for a later run to pick up."""
    dest = tmp_path / "model.bin"

    def fake_urlretrieve(url, target):
        with open(target, "wb") as handle:
            handle.write(b"malicious payload")

    monkeypatch.setattr(model_store.urllib.request, "urlretrieve", fake_urlretrieve)
    with pytest.raises(ModelIntegrityError):
        model_store._download("https://example.invalid/m.bin", dest,
                              label="test", sha256=hashlib.sha256(b"good").hexdigest())

    assert not dest.exists(), "tampered artifact was cached"
    assert not dest.with_suffix(".bin.part").exists(), "temp file left behind"


def test_cached_file_is_rechecked_not_trusted(tmp_path, monkeypatch):
    """An artifact already on disk still has to match -- it may have been swapped."""
    monkeypatch.setenv("STASHPIX_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("STASHPIX_SYNCSEAL", raising=False)
    (model_store.models_dir() / model_store.SYNCSEAL_FILENAME).write_bytes(b"swapped")

    with pytest.raises(ModelIntegrityError):
        model_store.resolve_syncseal_path(download=False)


def test_env_override_is_also_verified(tmp_path, monkeypatch):
    """An operator-supplied path is a path, not a reason to skip the check."""
    monkeypatch.setenv("STASHPIX_HOME", str(tmp_path / "home"))
    rogue = _write(tmp_path, "rogue.pt", b"not the real model")
    monkeypatch.setenv("STASHPIX_SYNCSEAL", str(rogue))

    with pytest.raises(ModelIntegrityError):
        model_store.resolve_syncseal_path(download=False)


def test_params_url_is_pinned_to_a_commit_not_a_branch():
    """A raw.githubusercontent URL on `main` serves whatever is there today."""
    assert "/main/" not in model_store.WAM_PARAMS_URL
    assert WAM_REPO_COMMIT in model_store.WAM_PARAMS_URL
