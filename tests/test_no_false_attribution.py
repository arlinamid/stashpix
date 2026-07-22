"""A message may only ever come from bits actually present in the image.

v1.4.0 shipped an ``edge_match`` fallback that resolved a registry entry by
perceptual-hash similarity alone. Because the robust watermark is invisible, an
unwatermarked copy of the original cover had fingerprint distance 0 from the
stored reference — so ``extract`` returned the owner's message for an image that
carried no watermark at all. The layer was removed in v1.5.0; these tests keep
it from coming back.
"""

from __future__ import annotations

import io
import os

import pytest
from PIL import Image, ImageFilter

from stashpix.config import EmbedConfig, ExtractConfig

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
MSG = "Owner claim — must not leak"
KEY = "attribution-key"


def _cover(name: str, width: int = 768) -> Image.Image:
    img = Image.open(os.path.join(ASSETS, name)).convert("RGB")
    w, h = img.size
    return img.resize((width, max(1, round(width * h / w))), Image.LANCZOS)


@pytest.fixture()
def marked(engine, tmp_path):
    """Embed into landscape_sky and return (original_cover, stego_image)."""
    original = _cover("landscape_sky.png")
    src = tmp_path / "cover.png"
    original.save(src)
    out = tmp_path / "stego.png"
    engine.embed_file(str(src), MSG, str(out), EmbedConfig(key=KEY, enable_lsb=False))
    return original, Image.open(out).convert("RGB")


def test_stego_image_still_resolves(engine, marked):
    """Control: the genuinely watermarked image must resolve."""
    _, stego = marked
    msg, info = engine.extract(stego, ExtractConfig(key=KEY))
    assert msg == MSG
    assert info["layer_key"] == "robust"


def test_original_unmarked_cover_is_not_attributed(engine, marked):
    """The exact cover the watermark was embedded into carries no bits."""
    original, _ = marked
    msg, info = engine.extract(original, ExtractConfig(key=KEY))
    assert msg is None
    assert info.get("layer_key") is None
    assert info.get("robust_id") is None


def test_jpeg_of_unmarked_cover_is_not_attributed(engine, marked, tmp_path):
    original, _ = marked
    buf = io.BytesIO()
    original.save(buf, "JPEG", quality=30)
    buf.seek(0)
    msg, info = engine.extract(Image.open(buf).convert("RGB"), ExtractConfig(key=KEY))
    assert msg is None
    assert info.get("layer_key") is None


def test_visually_similar_foreign_image_is_not_attributed(engine, marked):
    """A different photo of the same genre must never resolve."""
    foreign = _cover("beach_horizon.png")
    msg, info = engine.extract(foreign, ExtractConfig(key=KEY))
    assert msg is None
    assert info.get("layer_key") is None


def test_heavy_blur_destroys_the_mark_rather_than_guessing(engine, marked):
    """σ=2 blur is beyond the mid-band DCT ID — it must fail closed, not guess."""
    _, stego = marked
    blurred = stego.filter(ImageFilter.GaussianBlur(radius=2))
    msg, info = engine.extract(blurred, ExtractConfig(key=KEY))
    assert msg is None, "must report failure rather than fall back to image similarity"
    assert info.get("layer_key") is None


def test_stylized_full_frame_edit_is_not_attributed(engine, marked):
    """Sketch/edge-filter style edits destroy the mark; no similarity fallback."""
    import numpy as np
    from PIL import ImageOps

    _, stego = marked
    gray = np.asarray(stego.convert("L"), dtype=np.float32)
    gy, gx = np.gradient(gray)
    mag = np.hypot(gx, gy)
    mag = mag / (mag.max() or 1.0)
    edge = Image.fromarray(np.stack([mag * 255.0] * 3, axis=-1).astype(np.uint8))
    stylized = Image.blend(ImageOps.grayscale(stego).convert("RGB"), edge, 0.85)

    msg, info = engine.extract(stylized, ExtractConfig(key=KEY))
    assert msg is None
    assert info.get("layer_key") is None


def test_registry_has_no_similarity_resolver():
    """The removed API must not reappear on the Registry."""
    from stashpix.registry import Registry

    assert not hasattr(Registry, "resolve_fingerprint")


def test_extract_config_has_no_edge_match_knobs():
    cfg = ExtractConfig(key=KEY)
    for field in ("edge_match", "edge_match_max_dist", "edge_match_relaxed"):
        assert not hasattr(cfg, field)
