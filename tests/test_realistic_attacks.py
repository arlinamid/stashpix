"""Realistic edits: mild blur / JPEG / crop / piece-on-canvas."""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageEnhance, ImageFilter

from stashpix.config import EmbedConfig, ExtractConfig

from tests.geo_helpers import place_on_green, require_cv2

MSG = "Realistic attack test — hello"
KEY = "pw42"


@pytest.fixture()
def stego_img(engine, large_photo_path, tmp_path):
    out = tmp_path / "stego.png"
    engine.embed_file(large_photo_path, MSG, str(out), EmbedConfig(key=KEY, lsb_copies=2))
    return Image.open(out).convert("RGB"), str(out)


def _extract(engine, img, path, key=KEY, ref=None):
    img.save(path)
    if ref:
        return engine.extract_geo_file(str(path), ref, ExtractConfig(key=key))
    return engine.extract_file(str(path), ExtractConfig(key=key))


@pytest.mark.parametrize("label,transform", [
    ("blur1", lambda im: im.filter(ImageFilter.GaussianBlur(1))),
    ("sharpen", lambda im: im.filter(ImageFilter.SHARPEN)),
    ("contrast", lambda im: ImageEnhance.Contrast(im).enhance(1.3)),
    ("grayscale", lambda im: im.convert("L").convert("RGB")),
    ("scale80", lambda im: im.resize((int(im.width * 0.8), int(im.height * 0.8)),
                                     Image.LANCZOS)),
])
def test_full_image_mild_edits(engine, stego_img, tmp_path, label, transform):
    img, _ = stego_img
    msg, info = _extract(engine, transform(img), tmp_path / f"{label}.png")
    assert msg == MSG
    assert info.get("layer_key") in ("lsb", "robust")


def test_full_image_jpeg50(engine, stego_img, tmp_path):
    img, _ = stego_img
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=50)
    buf.seek(0)
    jpg = Image.open(buf).convert("RGB")
    msg, info = _extract(engine, jpg, tmp_path / "jpeg50.png")
    assert msg == MSG
    assert info["layer_key"] == "robust"


def test_keep75_crop_and_jpeg(engine, stego_img, tmp_path):
    img, _ = stego_img
    w, h = img.size
    big = img.crop((w // 8, h // 8, w - w // 8, h - h // 8))
    msg, _ = _extract(engine, big, tmp_path / "keep75.png")
    assert msg == MSG
    buf = io.BytesIO()
    big.save(buf, "JPEG", quality=60)
    buf.seek(0)
    msg2, info = _extract(engine, Image.open(buf).convert("RGB"), tmp_path / "keep75_jpg.png")
    assert msg2 == MSG
    assert info["layer_key"] == "robust"


def test_piece_on_green_with_reference(engine, stego_img, tmp_path):
    require_cv2()
    img, stego_path = stego_img
    w, h = img.size
    cw, ch = int(w * 0.55), int(h * 0.55)
    piece = img.crop(((w - cw) // 2, (h - ch) // 2, (w + cw) // 2, (h + ch) // 2))
    scene = place_on_green(piece, occlude_frac=0.0, pad=60)
    # enlarge canvas feel: paste onto full-size green
    canvas = Image.new("RGB", (w, h), (0, 180, 0))
    canvas.paste(piece, ((w - cw) // 2, (h - ch) // 2))
    msg, info = _extract(engine, canvas, tmp_path / "piece_green.png", ref=stego_path)
    assert msg == MSG
    assert info.get("layer_key") in ("robust", "geo_tps", "lsb")
