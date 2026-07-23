"""Image metadata: preserve the source's, stamp authorship fields, don't lie.

The old pipeline saved with a bare ``img.save(path)``, silently dropping the
source's EXIF/ICC. And metadata is a *label*, not proof — these tests keep both
properties honest: source metadata survives, our fields are written and readable,
and none of it disturbs the pixels the LSB/robust layers rely on.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from stashpix import settings
from stashpix.config import EmbedConfig, ExtractConfig
from stashpix.core.imaging import save_lossless
from stashpix.core.metadata import ImageMetadata, read_metadata, save_kwargs

AUTHOR = "Jane Photographer"
COPY = "© 2026 Jane Photographer"
KEY = "meta-key"
MSG = "metadata test"


# --------------------------------------------------------------- settings

def test_settings_defaults_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("STASHPIX_HOME", str(tmp_path / "home"))
    prefs = settings.load()
    assert prefs["sign"] is True
    assert prefs["write_metadata"] is True
    assert prefs["author"] == ""


def test_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("STASHPIX_HOME", str(tmp_path / "home"))
    settings.save({"author": AUTHOR, "copyright_notice": COPY})
    prefs = settings.load()
    assert prefs["author"] == AUTHOR
    assert prefs["copyright_notice"] == COPY
    # unknown keys are ignored, not stored
    settings.save({"bogus": 1})
    assert "bogus" not in settings.load()


def test_settings_set_rejects_unknown_key(tmp_path, monkeypatch):
    monkeypatch.setenv("STASHPIX_HOME", str(tmp_path / "home"))
    with pytest.raises(KeyError):
        settings.set("nope", 1)


# --------------------------------------------------------------- metadata io

def _png(tmp_path, name="src.png", size=(64, 64)):
    arr = np.random.default_rng(0).integers(0, 256, (*size, 3), dtype=np.uint8)
    p = tmp_path / name
    Image.fromarray(arr, "RGB").save(p)
    return p


def test_authorship_fields_written_and_readable(tmp_path):
    img = Image.open(_png(tmp_path)).convert("RGB")
    meta = ImageMetadata(author=AUTHOR, copyright_notice=COPY,
                         watermark_id="deadbeef", signed_by="58a3cfabd766b452")
    out = tmp_path / "out.png"
    save_lossless(img, str(out), metadata=meta)

    read = read_metadata(Image.open(out))
    assert read.get("author") == AUTHOR
    assert read.get("copyright_notice") == COPY
    assert read.get("watermark_id") == "deadbeef"
    assert read.get("signed_by") == "58a3cfabd766b452"


def test_source_exif_is_preserved(tmp_path):
    # Give the source a distinctive EXIF Artist, then save through our pipeline
    # WITHOUT supplying metadata -> the source value must survive.
    src = Image.open(_png(tmp_path)).convert("RGB")
    exif = src.getexif()
    exif[0x013B] = "Original Camera Owner"
    src_path = tmp_path / "withexif.png"
    src.save(src_path, exif=exif.tobytes())

    reopened = Image.open(src_path)
    out = tmp_path / "out.png"
    save_lossless(reopened.convert("RGB"), str(out), source=reopened)

    assert read_metadata(Image.open(out)).get("author") == "Original Camera Owner"


def test_our_fields_layer_over_source(tmp_path):
    src = Image.open(_png(tmp_path)).convert("RGB")
    exif = src.getexif()
    exif[0x013B] = "Camera Owner"
    src_path = tmp_path / "withexif.png"
    src.save(src_path, exif=exif.tobytes())
    reopened = Image.open(src_path)

    out = tmp_path / "out.png"
    save_lossless(reopened.convert("RGB"), str(out),
                  metadata=ImageMetadata(author=AUTHOR), source=reopened)
    assert read_metadata(Image.open(out)).get("author") == AUTHOR


def test_metadata_does_not_touch_pixels(tmp_path):
    img = Image.open(_png(tmp_path)).convert("RGB")
    before = np.asarray(img).copy()
    out = tmp_path / "out.png"
    save_lossless(img, str(out),
                  metadata=ImageMetadata(author=AUTHOR, watermark_id="x"))
    after = np.asarray(Image.open(out).convert("RGB"))
    assert np.array_equal(before, after)


# ------------------------------------------------------------- through engine

def test_embed_writes_metadata_and_preserves_lsb(engine, photo_path, tmp_path):
    out = tmp_path / "stego.png"
    res = engine.embed_file(photo_path, MSG, str(out),
                            EmbedConfig(key=KEY, author=AUTHOR, copyright_notice=COPY))
    assert res.info.get("metadata") == "written"

    read = read_metadata(Image.open(out))
    assert read.get("author") == AUTHOR
    assert read.get("watermark_id") == res.robust_id
    # signer fingerprint stamped from the authorship signature
    assert read.get("signed_by") == res.info.get("signed_by")

    # the message still decodes -> metadata did not disturb the hidden data
    msg, _ = engine.extract_file(str(out), ExtractConfig(key=KEY))
    assert msg == MSG


def test_no_metadata_flag_skips_authorship_fields(engine, photo_path, tmp_path):
    out = tmp_path / "stego.png"
    res = engine.embed_file(photo_path, MSG, str(out),
                            EmbedConfig(key=KEY, author=AUTHOR, write_metadata=False))
    assert "metadata" not in res.info
    read = read_metadata(Image.open(out))
    assert read.get("author") != AUTHOR
    # data still recoverable
    msg, _ = engine.extract_file(str(out), ExtractConfig(key=KEY))
    assert msg == MSG


def test_metadata_is_not_treated_as_proof(engine, photo_path, tmp_path):
    """Editing the EXIF author must NOT change the verified authorship verdict.

    The signature — not the label — is what extract trusts. This guards against
    ever wiring metadata into the attribution decision.
    """
    out = tmp_path / "stego.png"
    res = engine.embed_file(photo_path, MSG, str(out),
                            EmbedConfig(key=KEY, author=AUTHOR))

    # Forge the EXIF author on the stego file.
    forged = Image.open(out).convert("RGB")
    ex = forged.getexif()
    ex[0x013B] = "Impostor"
    forged.save(out, exif=ex.tobytes(),
                pnginfo=__import__("PIL.PngImagePlugin", fromlist=["PngInfo"]).PngInfo())

    msg, info = engine.extract_file(str(out), ExtractConfig(key=KEY))
    assert msg == MSG
    # authorship verdict comes from the signature, unaffected by the forged label
    assert info["authorship"]["valid"] is True
    assert info["authorship"]["signer"] == res.info.get("signed_by")
