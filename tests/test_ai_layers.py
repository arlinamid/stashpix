"""Optional SyncSeal / WAM smoke tests (skip when models are unavailable)."""

from __future__ import annotations

import os

import pytest
from PIL import Image

from stashpix.config import EmbedConfig, ExtractConfig
from stashpix.core.model_store import resolve_syncseal_path, resolve_wam_checkpoint
from stashpix.layers.syncseal import SyncSealLayer, torch_available as sync_torch_ok
from stashpix.layers.wam_local import WamLocalLayer, id_hex_to_bits, bits_to_hex


MSG = "AI layer smoke — hello"
KEY = "pw"


def test_ai_flags_off_by_default(engine, photo_path):
    img = Image.open(photo_path).convert("RGB")
    _, info = engine.embed(img, MSG, EmbedConfig(key=KEY, enable_lsb=False))
    assert "wam" not in info["layers"]
    assert "syncseal" not in info["layers"]


def test_wam_fingerprint_deterministic():
    a = id_hex_to_bits("2e2e453698a04e20a967248a11b63753")
    b = id_hex_to_bits("2e2e453698a04e20a967248a11b63753")
    assert a == b
    assert len(a) == 32
    assert bits_to_hex(a) == bits_to_hex(b)


@pytest.mark.skipif(not sync_torch_ok(), reason="torch not installed")
def test_syncseal_roundtrip_if_model(engine, photo_path, tmp_path, monkeypatch):
    monkeypatch.setenv("STASHPIX_HOME", str(tmp_path / "home"))
    path = resolve_syncseal_path(download=False)
    if path is None:
        # Attempt download once; skip if offline / blocked
        path = resolve_syncseal_path(download=True)
    if path is None:
        pytest.skip("SyncSeal checkpoint not available")

    layer = SyncSealLayer()
    if not layer.available(download=False):
        pytest.skip(layer.last_error() or "SyncSeal unavailable")

    out = tmp_path / "sync.png"
    res = engine.embed_file(
        photo_path, MSG, str(out),
        EmbedConfig(key=KEY, enable_lsb=False, enable_syncseal=True),
    )
    assert "syncseal" in res.info.get("layers", []) or res.info.get("syncseal_skipped")
    if res.info.get("syncseal_skipped"):
        pytest.skip(res.info["syncseal_skipped"])

    msg, info = engine.extract_file(
        str(out), ExtractConfig(key=KEY, try_syncseal=True),
    )
    assert msg == MSG
    assert info.get("layer_key") == "robust"


@pytest.mark.skipif(not sync_torch_ok(), reason="torch not installed")
def test_wam_roundtrip_if_model(engine, photo_path, tmp_path, monkeypatch):
    monkeypatch.setenv("STASHPIX_HOME", str(tmp_path / "home"))
    if resolve_wam_checkpoint(download=False) is None:
        if resolve_wam_checkpoint(download=True) is None:
            pytest.skip("WAM checkpoint not available")

    layer = WamLocalLayer()
    if not layer.available(download=True):
        pytest.skip(layer.last_error() or "WAM unavailable")

    out = tmp_path / "wam.png"
    res = engine.embed_file(
        photo_path, MSG, str(out),
        EmbedConfig(key=KEY, enable_lsb=False, enable_wam=True),
    )
    if res.info.get("wam_skipped"):
        pytest.skip(str(res.info["wam_skipped"]))
    assert "wam" in res.info.get("layers", [])

    msg, info = engine.extract_file(
        str(out), ExtractConfig(key=KEY, try_wam=True),
    )
    assert msg == MSG
    assert info.get("layer_key") == "robust"
    assert info.get("wam_fingerprint")
