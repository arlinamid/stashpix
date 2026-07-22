"""The robust DCT layer must recover its ID from every cover, every time.

v1.4.0 derived the QIM step from the coefficient QIM had just modified, so the
encoder and the blind decoder disagreed about the lattice: measured at 24.8%
median step mismatch, and a clean lossless roundtrip on city_architecture.png
succeeded only 4 times out of 10. Raising ``strength`` made it worse, not better.

v1.5.0 derives the step only from quantities the embedder never touches (DC
luminance + AC energy outside the carrier cells) and verifies the mark reads
back before returning. These tests pin both properties down.
"""

from __future__ import annotations

import glob
import io
import os

import numpy as np
import pytest
from PIL import Image, ImageFilter

from stashpix.config import EmbedConfig, ExtractConfig
from stashpix.layers.robust import RobustWatermarkLayer, STRENGTH_LADDER

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
KEY = "reliability-key"
MSG = "Reliability probe"

STOCK_COVERS = sorted(
    p for p in glob.glob(os.path.join(ASSETS, "*.png"))
    if not os.path.basename(p).endswith("_stashpix.png")
)

# Every embed draws a fresh random UUID, so repeating the embed samples
# different frame payloads on the same cover -- which is exactly how the v1.4.0
# flakiness showed up (some IDs decoded, some did not).
REPEATS = 5


def _cover(path: str, width: int = 768) -> Image.Image:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    return img.resize((width, max(1, round(width * h / w))), Image.LANCZOS)


def _embed(engine, tmp_path, cover: Image.Image, **kw):
    src = tmp_path / "cover.png"
    cover.save(src)
    out = tmp_path / "stego.png"
    res = engine.embed_file(str(src), MSG, str(out),
                            EmbedConfig(key=KEY, enable_lsb=False, **kw))
    return res, Image.open(out).convert("RGB")


# --------------------------------------------------------------- reliability

@pytest.mark.parametrize("cover_path", STOCK_COVERS,
                         ids=[os.path.basename(p) for p in STOCK_COVERS])
def test_clean_roundtrip_is_reliable_on_every_cover(engine, tmp_path, cover_path):
    """No cover may be flaky: every repeat must recover its own ID."""
    cover = _cover(cover_path)
    layer = RobustWatermarkLayer(engine.registry)
    for i in range(REPEATS):
        res, stego = _embed(engine, tmp_path, cover)
        result = layer.extract(stego, ExtractConfig(key=KEY))
        assert result is not None, f"repeat {i}: frame lost on a lossless roundtrip"
        assert result.info["id"] == res.robust_id, f"repeat {i}: wrong ID recovered"


def test_embed_self_verifies_before_returning(engine, tmp_path):
    res, _ = _embed(engine, tmp_path, _cover(os.path.join(ASSETS, "landscape_sky.png")))
    info = res.info["robust"]
    assert info["self_verified"] is True
    assert info["strength"] > 0
    assert 1 <= info["attempts"] <= len(STRENGTH_LADDER)


def test_extract_finds_the_mark_when_embed_escalated(engine, tmp_path):
    """A raised embed strength must still be found by the decoder's sweep.

    The QIM step scales linearly with strength, so an escalated embed is on a
    different lattice than the caller's base strength -- the decoder has to
    sweep the ladder to find it.
    """
    cover = _cover(os.path.join(ASSETS, "city_architecture.png"))
    layer = RobustWatermarkLayer(engine.registry)
    for _ in range(REPEATS):
        res, stego = _embed(engine, tmp_path, cover)
        # Decode with the *base* strength, as any normal caller would.
        result = layer.extract(stego, ExtractConfig(key=KEY))
        assert result is not None
        assert result.info["id"] == res.robust_id


@pytest.mark.parametrize("strength", [1.0, 2.0, 3.0, 4.0, 6.0])
def test_strength_never_breaks_the_roundtrip(engine, tmp_path, strength):
    """Turning strength up must never lose the mark.

    In v1.4.0 strength 6.0 failed 10/10 on five of six covers, because a bigger
    modulation meant a bigger encoder/decoder step disagreement.
    """
    cover = _cover(os.path.join(ASSETS, "landscape_sky.png"))
    res, stego = _embed(engine, tmp_path, cover, robust_strength=strength)
    result = RobustWatermarkLayer(engine.registry).extract(
        stego, ExtractConfig(key=KEY, robust_strength=strength))
    assert result is not None
    assert result.info["id"] == res.robust_id


# ------------------------------------------------------------- the mechanism

def test_qim_step_is_invariant_under_embedding(engine, tmp_path):
    """The decoder must derive the same step the encoder used.

    This is the root-cause test: measure the step both sides compute for the
    same block, from the clean and the watermarked image respectively.
    """
    from stashpix.core.dct import dct2, luminance_slack, DC0, MIN_DELTA
    from stashpix.core.watermark_frame import (
        COEFS_MID, adaptive_strength_scale, block_ac_energy,
    )

    cover = _cover(os.path.join(ASSETS, "city_architecture.png"))
    res, stego = _embed(engine, tmp_path, cover)
    strength = res.info["robust"]["strength"]

    w, h = cover.size
    cw, ch = 512, round(512 * h / w)
    cw -= cw % 8
    ch -= ch % 8
    y_clean = np.array(cover.resize((cw, ch), Image.LANCZOS)
                       .convert("YCbCr").split()[0], np.float64)
    y_stego = np.array(stego.resize((cw, ch), Image.LANCZOS)
                       .convert("YCbCr").split()[0], np.float64)

    drift = []
    for by in range(ch // 8):
        for bx in range(cw // 8):
            cc = dct2(y_clean[by * 8:by * 8 + 8, bx * 8:bx * 8 + 8])
            cs = dct2(y_stego[by * 8:by * 8 + 8, bx * 8:bx * 8 + 8])
            scale_c = adaptive_strength_scale(block_ac_energy(cc, COEFS_MID))
            if scale_c <= 0:
                continue
            scale_s = adaptive_strength_scale(block_ac_energy(cs, COEFS_MID))
            lum_c = luminance_slack(cc, DC0)
            lum_s = luminance_slack(cs, DC0)
            for cu, cv in COEFS_MID:
                enc = max(MIN_DELTA, strength * scale_c * lum_c[cu, cv])
                dec = max(MIN_DELTA, strength * scale_s * lum_s[cu, cv])
                drift.append(abs(dec - enc) / enc)

    drift = np.array(drift)
    assert len(drift) > 500
    # v1.4.0 measured: median 24.8%, 49.8% above 25%, 29.2% above 50%.
    # v1.5.0 measured: median 5.75%.
    #
    # The residual is NOT the self-masking feedback loop this change removed --
    # it is the canonical-size resize round trip (768 -> 512 -> 768 -> 512) plus
    # 8-bit quantization nudging DC and AC energy. That noise floor is inherent
    # to embedding at a canonical scale for resize invariance. The tail comes
    # from blocks sitting just above AC_GATE, where the scale approaches 0 and a
    # small energy wobble moves the step a lot; see the KNOWN LIMIT note on
    # adaptive_strength_scale.
    #
    # The threshold sits between the two measurements: loose enough for the
    # resize noise floor, tight enough that reintroducing a coefficient-dependent
    # step fails this immediately. Only the median is asserted -- the tail shape
    # has not been measured, and a guessed bound would be a flaky test rather
    # than a real guarantee.
    assert np.median(drift) < 0.10, f"median step drift {np.median(drift):.2%}"


def test_carrier_coefficients_excluded_from_texture_measure():
    """block_ac_energy must ignore exactly the cells QIM writes to."""
    from stashpix.core.watermark_frame import COEFS_MID, block_ac_energy

    rng = np.random.default_rng(0)
    coef = rng.normal(0, 50, (8, 8))
    before = block_ac_energy(coef, COEFS_MID)
    for cu, cv in COEFS_MID:
        coef[cu, cv] += 500.0          # a change far larger than any real embed
    assert block_ac_energy(coef, COEFS_MID) == pytest.approx(before)


def test_luminance_slack_ignores_the_carrier_cells():
    from stashpix.core.dct import luminance_slack
    from stashpix.core.watermark_frame import COEFS_MID

    rng = np.random.default_rng(1)
    coef = rng.normal(0, 50, (8, 8))
    coef[0, 0] = 900.0
    before = luminance_slack(coef).copy()
    for cu, cv in COEFS_MID:
        coef[cu, cv] += 500.0
    assert np.allclose(luminance_slack(coef), before)


# ------------------------------------------------------------------ attacks

@pytest.mark.parametrize("label,attack", [
    ("jpeg60", lambda im: _jpeg(im, 60)),
    ("jpeg40", lambda im: _jpeg(im, 40)),
    ("blur1", lambda im: im.filter(ImageFilter.GaussianBlur(1))),
    ("scale80", lambda im: im.resize((int(im.width * .8), int(im.height * .8)),
                                     Image.LANCZOS)),
])
def test_survives_common_edits(engine, tmp_path, label, attack):
    cover = _cover(os.path.join(ASSETS, "sample.png"))
    res, stego = _embed(engine, tmp_path, cover)
    result = RobustWatermarkLayer(engine.registry).extract(
        attack(stego), ExtractConfig(key=KEY))
    assert result is not None, f"{label}: frame lost"
    assert result.info["id"] == res.robust_id


def _jpeg(img: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).convert("RGB")
