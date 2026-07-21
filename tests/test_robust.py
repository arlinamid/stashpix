"""Robust DCT watermark tests."""

import io

from PIL import Image

from stegosuite.layers.robust import RobustWatermarkLayer
from stegosuite.config import EmbedConfig, ExtractConfig


def _jpeg(img, q):
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=q)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def test_robust_survives_jpeg(photo_path, tmp_registry):
    layer = RobustWatermarkLayer(tmp_registry)
    img = Image.open(photo_path).convert("RGB")
    outcome = layer.embed(img, "message via registry", EmbedConfig(key="pw"))
    attacked = _jpeg(outcome.image, 60)
    result = layer.extract(attacked, ExtractConfig(key="pw"))
    assert result is not None
    assert result.message == "message via registry"


def test_robust_wrong_key_no_result(photo_path, tmp_registry):
    layer = RobustWatermarkLayer(tmp_registry)
    img = Image.open(photo_path).convert("RGB")
    outcome = layer.embed(img, "msg", EmbedConfig(key="pw"))
    result = layer.extract(outcome.image, ExtractConfig(key="different"))
    assert result is None or result.message != "msg"
