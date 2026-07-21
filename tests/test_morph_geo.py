"""Morph / non-linear geometric recovery (SIFT + TPS + flow layer)."""

from __future__ import annotations

import pytest
from PIL import Image

from stegosuite.config import EmbedConfig, ExtractConfig

from tests.geo_helpers import elastic, perspective, require_cv2, swirl, wave

MSG = "Morph geo test message — áéíőű"
KEY = "000101"


@pytest.fixture()
def stego_pair(engine, large_photo_path, tmp_path):
    """Embed once; return (stego_path, message)."""
    require_cv2()
    out = tmp_path / "stego.png"
    engine.embed_file(large_photo_path, MSG, str(out),
                      EmbedConfig(key=KEY, lsb_copies=2, enable_lsb=True))
    return str(out), MSG


@pytest.mark.parametrize("name,fn,amt", [
    ("perspective", perspective, 0.10),
    ("wave", wave, 4),
    ("wave", wave, 10),
    ("elastic", elastic, 8),
    ("elastic", elastic, 25),
    ("swirl", swirl, 0.6),
    ("swirl", swirl, 1.0),
])
def test_morph_recovers_with_reference(engine, stego_pair, tmp_path, name, fn, amt):
    require_cv2()
    stego_path, expected = stego_pair
    attacked = fn(Image.open(stego_path).convert("RGB"), amt)
    path = tmp_path / f"morph_{name}_{amt}.png"
    attacked.save(path)
    msg, info = engine.extract_geo_file(str(path), stego_path, ExtractConfig(key=KEY))
    assert msg == expected
    assert info.get("layer_key") in ("robust", "geo_tps", "lsb")


def test_swirl_wrong_password_is_silent(engine, stego_pair, tmp_path):
    require_cv2()
    stego_path, _ = stego_pair
    attacked = swirl(Image.open(stego_path).convert("RGB"), 0.6)
    path = tmp_path / "swirl_fp.png"
    attacked.save(path)
    msg, _ = engine.extract_geo_file(str(path), stego_path, ExtractConfig(key="999999"))
    assert msg is None
