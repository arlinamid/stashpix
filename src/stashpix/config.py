"""Configuration objects and default constants.

Parameters used to live as scattered keyword arguments across many functions.
They are now grouped into typed dataclasses that flow through the engine and
layers, which makes the public API explicit and easy to extend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# --- LSB layer defaults ---------------------------------------------------
DEFAULT_NSYM = 64          # Reed-Solomon ECC bytes per 255-byte block
DEFAULT_COPIES = 3         # redundant LSB copies (combined pipeline default)

# --- Robust DCT watermark defaults ---------------------------------------
DEFAULT_METHOD = "jnd"     # "jnd" (perceptual, adaptive) or "qim" (legacy fixed step)
DEFAULT_Q = 26.0           # legacy fixed QIM step (method="qim")
DEFAULT_STRENGTH = 3.0     # JND strength multiplier (method="jnd")

# --- Visible watermark defaults ------------------------------------------
DEFAULT_VISIBLE_OPACITY = 0.20
DEFAULT_VISIBLE_ANGLE = 30.0
DEFAULT_VISIBLE_FONT_FRAC = 0.045
DEFAULT_VISIBLE_THRESHOLD = 0.15


@dataclass
class EmbedConfig:
    """Everything needed to embed all layers into a cover image."""

    key: Optional[str] = None

    # LSB
    enable_lsb: bool = True
    lsb_nsym: int = DEFAULT_NSYM
    lsb_copies: int = DEFAULT_COPIES
    lsb_self_verify: bool = True

    # Robust DCT watermark
    enable_robust: bool = True
    robust_method: str = DEFAULT_METHOD
    robust_strength: float = DEFAULT_STRENGTH
    robust_q: float = DEFAULT_Q
    robust_auto_adapt: bool = True   # per-block AC-energy JND scale (flat → skip)

    # Visible watermark (4th layer, optional)
    visible_text: Optional[str] = None
    visible_opacity: float = DEFAULT_VISIBLE_OPACITY
    visible_key: Optional[str] = None

    # Optional AI layers (default off; require torch + checkpoints)
    enable_wam: bool = False
    enable_syncseal: bool = False


@dataclass
class ExtractConfig:
    """Everything needed to extract a message with graceful degradation."""

    key: Optional[str] = None
    robust_method: Optional[str] = None   # None = auto (jnd -> qim)
    robust_strength: float = DEFAULT_STRENGTH
    robust_q: float = DEFAULT_Q
    robust_auto_adapt: bool = True
    reference_path: Optional[str] = None   # for geometric (SIFT) sync
    blind_geo: bool = True                 # reference-free deskew/crop fallback
    morph_geo: bool = True                 # SIFT+TPS fallback for non-linear morphs

    # Registry fingerprint fallback (blur when robust DCT bits are lost)
    edge_match: bool = True
    edge_match_max_dist: int = 18
    edge_match_min_gap: int = 4
    edge_match_relaxed: bool = True
    edge_match_relaxed_max_dist: int = 64
    edge_match_relaxed_min_gap: int = 8

    # Optional AI extract helpers (default off)
    try_wam: bool = False
    try_syncseal: bool = False


@dataclass
class VerifyConfig:
    """Parameters for visible-watermark verification."""

    text: str = ""
    key: Optional[str] = None
    threshold: float = DEFAULT_VISIBLE_THRESHOLD


__all__ = [
    "EmbedConfig",
    "ExtractConfig",
    "VerifyConfig",
    "DEFAULT_NSYM",
    "DEFAULT_COPIES",
    "DEFAULT_METHOD",
    "DEFAULT_Q",
    "DEFAULT_STRENGTH",
    "DEFAULT_VISIBLE_OPACITY",
    "DEFAULT_VISIBLE_ANGLE",
    "DEFAULT_VISIBLE_FONT_FRAC",
    "DEFAULT_VISIBLE_THRESHOLD",
]
