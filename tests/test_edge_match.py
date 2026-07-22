"""Registry fingerprint fallback when robust DCT bits are lost (e.g. heavy blur)."""

from __future__ import annotations

import os

import numpy as np
import pytest
from PIL import Image, ImageFilter, ImageOps

from stashpix.config import EmbedConfig, ExtractConfig

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
MSG = "Edge-match fallback test"
KEY = "edge-key"


def _stylized_edge_blend(img: Image.Image, *, t: float = 0.85) -> Image.Image:
    """Full-frame edge-heavy blend — mimics sketch filters (relaxed pass territory)."""
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    gy, gx = np.gradient(gray)
    mag = np.hypot(gx, gy)
    mag = mag / (mag.max() or 1.0)
    edge = Image.fromarray(np.stack([mag * 255.0] * 3, axis=-1).astype(np.uint8))
    base = ImageOps.grayscale(img).convert("RGB")
    return Image.blend(base, edge, t)


@pytest.fixture()
def landscape_stego(engine, tmp_path):
    src = os.path.join(ASSETS, "landscape_sky.png")
    out = tmp_path / "landscape_stego.png"
    engine.embed_file(
        src,
        MSG,
        str(out),
        EmbedConfig(key=KEY, enable_lsb=False, enable_robust=True),
    )
    return Image.open(out).convert("RGB"), str(out)


def test_edge_hash_blur_stable():
    from stashpix.core.perceptual import edge_hash_hex, hamming_hex

    orig = Image.open(os.path.join(ASSETS, "landscape_sky.png")).convert("RGB")
    ref = edge_hash_hex(orig)
    blurred = orig.filter(ImageFilter.GaussianBlur(radius=2))
    assert hamming_hex(ref, edge_hash_hex(blurred)) <= 4


def test_blur2_recovers_via_registry_fingerprint(engine, landscape_stego, tmp_path):
    img, _ = landscape_stego
    blurred = img.filter(ImageFilter.GaussianBlur(radius=2))
    path = tmp_path / "blur2.png"
    blurred.save(path)
    msg, info = engine.extract_file(
        str(path),
        ExtractConfig(key=KEY, edge_match=True),
    )
    assert msg == MSG
    assert info["layer_key"] == "edge_match"
    assert info.get("robust_id")


def test_stylized_full_image_uses_relaxed_pass(engine, landscape_stego):
    img, _ = landscape_stego
    stylized = _stylized_edge_blend(img, t=0.85)
    msg, info = engine.extract(stylized, ExtractConfig(key=KEY))
    assert msg == MSG
    assert info["layer_key"] == "edge_match"
    assert info["edge_match"]["mode"] == "relaxed"


def test_partial_crop_not_matched_by_relaxed_pass(engine, landscape_stego):
    img, _ = landscape_stego
    w, h = img.size
    crop = img.crop((int(w * 0.325), int(h * 0.325), int(w * 0.675), int(h * 0.675)))
    msg, info = engine.extract(crop, ExtractConfig(key=KEY))
    assert msg is None
    assert info.get("layer_key") is None


def test_wrong_key_blocks_edge_match(engine, landscape_stego):
    img, _ = landscape_stego
    blurred = img.filter(ImageFilter.GaussianBlur(radius=2))
    msg, info = engine.extract(blurred, ExtractConfig(key="wrong-key"))
    assert msg is None
    assert info.get("layer_key") is None


def test_blur2_robust_alone_fails(engine, landscape_stego, tmp_path):
    from stashpix.layers.robust import RobustWatermarkLayer

    img, _ = landscape_stego
    blurred = img.filter(ImageFilter.GaussianBlur(radius=2))
    robust = RobustWatermarkLayer(engine.registry)
    result = robust.extract(blurred, ExtractConfig(key=KEY))
    assert result is None or result.message is None


def test_resolve_fingerprint_requires_gap(tmp_path, noise_path):
    from stashpix.registry import Registry

    reg = Registry(str(tmp_path / "r.json"))
    img_a = Image.open(noise_path).convert("RGB")
    img_b = img_a.resize((img_a.width - 20, img_a.height - 10))
    reg.add("aaa", "one")
    reg.add("bbb", "two")
    reg.save_reference("aaa", img_a)
    reg.save_reference("bbb", img_b)
    resolved = reg.resolve_fingerprint(img_a, max_dist=999, min_gap=0)
    assert resolved is not None
    assert resolved[0] == "aaa"
