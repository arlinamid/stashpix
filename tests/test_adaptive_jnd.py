"""Adaptive JND strength scaling for invisible robust embed."""

from stashpix.core.watermark_frame import (
    AC_GATE,
    TEXTURE_FULL,
    adaptive_strength_scale,
)


def test_adaptive_scale_flat_is_zero():
    assert adaptive_strength_scale(AC_GATE) == 0.0
    assert adaptive_strength_scale(0.0) == 0.0


def test_adaptive_scale_textured_is_one():
    assert adaptive_strength_scale(TEXTURE_FULL) == 1.0
    assert adaptive_strength_scale(TEXTURE_FULL + 100) == 1.0


def test_adaptive_scale_mid_ramp():
    mid = (AC_GATE + TEXTURE_FULL) / 2
    s = adaptive_strength_scale(mid)
    assert 0.0 < s < 1.0
    assert abs(s - 0.5) < 1e-6
