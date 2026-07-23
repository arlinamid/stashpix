"""Adaptive JND strength scaling for the invisible robust embed.

The curve maps a block's embed-invariant AC energy to a strength multiplier:
skip below the gate, ramp to unity at full texture, then contrast-masking growth
above it.
"""

import pytest

from stashpix.core.watermark_frame import (
    AC_GATE,
    MAX_SCALE,
    MIN_USEFUL_SCALE,
    TEXTURE_FULL,
    adaptive_strength_scale,
)


def test_flat_blocks_are_skipped():
    assert adaptive_strength_scale(AC_GATE) == 0.0
    assert adaptive_strength_scale(0.0) == 0.0


def test_full_texture_is_unity():
    assert adaptive_strength_scale(TEXTURE_FULL) == pytest.approx(1.0)


def test_ramp_starts_at_the_floor_not_zero():
    """A scale approaching 0 above the gate makes the QIM step unstable: a few
    percent of resize-round-trip energy drift moves it ~100%. Measured, flooring
    the ramp cuts the >25% drift tail from ~10-13% to <1% with no invisibility
    cost (flat-region PSNR unchanged), so the ramp must not start near 0.
    """
    assert adaptive_strength_scale(AC_GATE + 1e-6) == pytest.approx(MIN_USEFUL_SCALE)
    a = adaptive_strength_scale(AC_GATE + 1.0)
    b = adaptive_strength_scale((AC_GATE + 1.0) * 1.1)
    assert abs(b - a) / a < 0.05          # 10% energy wobble barely moves the step


def test_mid_ramp_is_floored_linear():
    mid = (AC_GATE + TEXTURE_FULL) / 2
    expected = MIN_USEFUL_SCALE + (1.0 - MIN_USEFUL_SCALE) * 0.5
    assert adaptive_strength_scale(mid) == pytest.approx(expected)


def test_ramp_is_monotonic():
    prev = adaptive_strength_scale(AC_GATE + 0.01)
    for energy in range(int(AC_GATE) + 1, int(TEXTURE_FULL) + 1):
        cur = adaptive_strength_scale(float(energy))
        assert cur >= prev
        assert MIN_USEFUL_SCALE <= cur <= 1.0
        prev = cur


def test_texture_keeps_masking_above_full():
    """Above TEXTURE_FULL the scale must keep growing, capped at MAX_SCALE.

    This is what recovers the robustness given up by dropping Watson's
    per-coefficient self-masking term from the QIM step -- without it, textured
    blocks would be modulated no harder than a barely-textured one.
    """
    assert adaptive_strength_scale(TEXTURE_FULL * 2) > 1.0
    assert adaptive_strength_scale(TEXTURE_FULL * 1000) == pytest.approx(MAX_SCALE)
    assert adaptive_strength_scale(1e9) <= MAX_SCALE
