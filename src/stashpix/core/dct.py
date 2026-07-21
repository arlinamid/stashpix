"""8x8 DCT, QIM parity quantization, and Watson's perceptual JND model.

Used by the robust DCT watermark layer. Kept dependency-light (numpy only) so it
can be reused/tested in isolation.
"""

from __future__ import annotations

import numpy as np

# --- Watson (1993) luminance sensitivity threshold table for 8x8 DCT -------
# Smaller value = the eye is more sensitive to that frequency (top-left = low
# frequency). This gives the perceptual "slack"; the absolute scale is set by
# the strength knob, calibrated to our DCT normalization.
WATSON_T = np.array([
    [1.40, 1.01, 1.16, 1.66, 2.40, 3.43, 4.79, 6.56],
    [1.01, 1.45, 1.32, 1.52, 2.00, 2.71, 3.67, 4.93],
    [1.16, 1.32, 2.24, 2.59, 2.98, 3.64, 4.60, 5.88],
    [1.66, 1.52, 2.59, 3.77, 4.55, 5.30, 6.28, 7.60],
    [2.40, 2.00, 2.98, 4.55, 6.15, 7.46, 8.71, 10.17],
    [3.43, 2.71, 3.64, 5.30, 7.46, 9.62, 11.58, 13.51],
    [4.79, 3.67, 4.60, 6.28, 8.71, 11.58, 14.50, 17.29],
    [6.56, 4.93, 5.88, 7.60, 10.17, 13.51, 17.29, 21.15],
], dtype=np.float64)

LUM_EXP = 0.649    # Watson luminance-masking exponent
CM_W = 0.7         # contrast-masking (self-masking) exponent
MIN_DELTA = 1e-3   # numeric lower bound on the QIM step
DC0 = 1024.0       # FIXED reference DC for luminance masking (mid-gray ~ 8*128).
                   # Must be fixed (not image-mean) so a large local change
                   # (e.g. partial occlusion) cannot shift the embedding/reading
                   # step and desynchronize otherwise-intact blocks.


def _dct_matrix(N: int = 8) -> np.ndarray:
    n = np.arange(N)
    k = n.reshape(-1, 1)
    C = np.sqrt(2.0 / N) * np.cos(np.pi * (2 * n + 1) * k / (2 * N))
    C[0, :] = np.sqrt(1.0 / N)
    return C


_D = _dct_matrix(8)


def dct2(block: np.ndarray) -> np.ndarray:
    return _D @ block @ _D.T


def idct2(coef: np.ndarray) -> np.ndarray:
    return _D.T @ coef @ _D


def qim_embed(c: float, bit: int, step: float) -> float:
    """Quantization Index Modulation: snap ``c`` to the lattice cell whose parity
    encodes ``bit``."""
    k = round(c / step)
    if k % 2 != bit:
        k = k + 1 if (c / step - k) >= 0 else k - 1
    return k * step


def qim_extract(c: float, step: float) -> int:
    return int(round(c / step)) % 2


def block_slack(coef: np.ndarray, dc_mean: float = DC0) -> np.ndarray:
    """Per-coefficient Watson JND (just-noticeable difference) for an 8x8 block.

      1) frequency sensitivity: WATSON_T (fixed table)
      2) luminance masking: brighter block -> more slack (DC-proportional)
      3) contrast masking: an already energetic coefficient tolerates more

    The decoder recomputes this from the received image, so the QIM step matches
    on embed and read (blind detection).
    """
    dc = abs(coef[0, 0])
    t_lum = WATSON_T * (max(dc, 1.0) / dc_mean) ** LUM_EXP
    slack = np.maximum(t_lum, (np.abs(coef) ** CM_W) * (t_lum ** (1.0 - CM_W)))
    return slack


__all__ = [
    "WATSON_T",
    "LUM_EXP",
    "CM_W",
    "MIN_DELTA",
    "DC0",
    "dct2",
    "idct2",
    "qim_embed",
    "qim_extract",
    "block_slack",
]
