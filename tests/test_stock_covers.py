"""Roundtrip smoke tests on multiple stock cover images in tests/assets/."""

from __future__ import annotations

import glob
import io
import os

import pytest
from PIL import Image, ImageFilter

from stashpix.config import EmbedConfig, ExtractConfig

from tests.test_realistic_attacks import KEY, MSG

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
SAMPLE = os.path.join(ASSETS, "sample.png")
STOCK_COVERS = sorted(
    p for p in glob.glob(os.path.join(ASSETS, "*.png"))
    if os.path.basename(p) not in ("sample_stashpix.png",)
    and not os.path.basename(p).endswith("_stashpix.png")
)


def _resize_cover(path: str, width: int) -> Image.Image:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    return img.resize((width, max(1, round(width * h / w))), Image.LANCZOS)


@pytest.fixture(params=STOCK_COVERS, ids=[os.path.basename(p) for p in STOCK_COVERS])
def stock_cover_path(request, tmp_path):
    """768px-wide cover derived from each stock asset."""
    out = tmp_path / f"{os.path.splitext(os.path.basename(request.param))[0]}_768.png"
    _resize_cover(request.param, 768).save(out)
    return str(out)


def test_stock_clean_roundtrip(engine, stock_cover_path, tmp_path):
    out = tmp_path / "stego.png"
    engine.embed_file(
        stock_cover_path, MSG, str(out), EmbedConfig(key=KEY, lsb_copies=2),
    )
    msg, info = engine.extract_file(str(out), ExtractConfig(key=KEY))
    assert msg == MSG
    assert info.get("layer_key") in ("lsb", "robust")


def test_sample_blur1(engine, tmp_path):
    """Mild blur (σ=1) — same fixture as tests/test_realistic_attacks.py."""
    src = tmp_path / "cover.png"
    _resize_cover(SAMPLE, 768).save(src)
    out = tmp_path / "stego.png"
    engine.embed_file(str(src), MSG, str(out), EmbedConfig(key=KEY, lsb_copies=2))
    blur = Image.open(out).convert("RGB").filter(ImageFilter.GaussianBlur(1))
    msg, info = engine.extract(blur, ExtractConfig(key=KEY))
    assert msg == MSG
    assert info.get("layer_key") in ("lsb", "robust")


def test_sample_jpeg60_robust(engine, tmp_path):
    src = tmp_path / "cover.png"
    _resize_cover(SAMPLE, 768).save(src)
    out = tmp_path / "stego.png"
    engine.embed_file(str(src), MSG, str(out), EmbedConfig(key=KEY, enable_lsb=False))
    buf = io.BytesIO()
    Image.open(out).convert("RGB").save(buf, "JPEG", quality=60)
    buf.seek(0)
    msg, info = engine.extract(Image.open(buf).convert("RGB"), ExtractConfig(key=KEY))
    assert msg == MSG
    assert info.get("layer_key") == "robust"
