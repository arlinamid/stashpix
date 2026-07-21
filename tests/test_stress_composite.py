"""Composite stress: morph + scale 80% + green canvas + partial occlusion."""

from __future__ import annotations

import pytest
from PIL import Image

from stashpix.config import EmbedConfig, ExtractConfig

from tests.geo_helpers import place_on_green, require_cv2, swirl

MSG = "Green stress — áéíőű"
KEY = "000101"


@pytest.fixture()
def stego_path(engine, large_photo_path, tmp_path):
    require_cv2()
    out = tmp_path / "stego.png"
    engine.embed_file(large_photo_path, MSG, str(out), EmbedConfig(key=KEY, lsb_copies=2))
    return str(out)


def _scene(stego_path: str, occlude: float) -> Image.Image:
    stego = Image.open(stego_path).convert("RGB")
    w0, h0 = stego.size
    morphed = swirl(stego, 0.6)
    small = morphed.resize((int(w0 * 0.80), int(h0 * 0.80)), Image.LANCZOS)
    return place_on_green(small, occlude_frac=occlude, pad=80)


@pytest.mark.parametrize("occlude", [0.0, 0.30, 0.50])
def test_morph80_green_occlusion(engine, stego_path, tmp_path, occlude):
    require_cv2()
    scene = _scene(stego_path, occlude)
    path = tmp_path / f"green_occ{int(occlude * 100)}.png"
    scene.save(path)
    msg, info = engine.extract_geo_file(str(path), stego_path, ExtractConfig(key=KEY))
    assert msg == MSG
    assert info.get("layer_key") in ("robust", "geo_tps")


def test_morph80_green_50_wrong_password(engine, stego_path, tmp_path):
    require_cv2()
    scene = _scene(stego_path, 0.50)
    path = tmp_path / "green_fp.png"
    scene.save(path)
    msg, _ = engine.extract_geo_file(str(path), stego_path, ExtractConfig(key="999999"))
    assert msg is None
