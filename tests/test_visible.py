"""Visible watermark tests."""

from PIL import Image

from stashpix.layers.visible import VisibleWatermarkLayer


def test_visible_present_after_apply(photo_path):
    layer = VisibleWatermarkLayer()
    img = Image.open(photo_path).convert("RGB")
    stamped = layer.apply(img, "(c) Test 2026", key="pw", opacity=0.20)
    present, score, _ = layer.verify(stamped, "(c) Test 2026", key="pw")
    assert present is True
    assert score >= 0.15


def test_visible_wrong_text_absent(photo_path):
    layer = VisibleWatermarkLayer()
    img = Image.open(photo_path).convert("RGB")
    stamped = layer.apply(img, "(c) Test 2026", key="pw", opacity=0.20)
    present, _, _ = layer.verify(stamped, "(c) Someone Else 2026", key="pw")
    assert present is False


def test_visible_wrong_key_absent(photo_path):
    layer = VisibleWatermarkLayer()
    img = Image.open(photo_path).convert("RGB")
    stamped = layer.apply(img, "(c) Test 2026", key="pw", opacity=0.20)
    present, _, _ = layer.verify(stamped, "(c) Test 2026", key="wrong")
    assert present is False
