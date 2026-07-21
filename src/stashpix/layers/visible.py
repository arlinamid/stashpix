"""Visible watermark layer — a human-readable diagonal stamp + its verification.

Fourth layer alongside the three invisible ones. The key controls the stamp
ANGLE (not just phase), giving it a real role in verification: verification uses
a translation-invariant (FFT peak), multi-scale normalized cross-correlation of
the expected stamp's edge pattern against the image's edge map — JPEG/resize
tolerant, and rejects wrong text/key/no-mark (no false positives).
"""

from __future__ import annotations

import math
import hashlib
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..core.base import Layer, EmbedOutcome, LayerResult
from ..config import (
    DEFAULT_VISIBLE_OPACITY,
    DEFAULT_VISIBLE_ANGLE,
    DEFAULT_VISIBLE_FONT_FRAC,
    DEFAULT_VISIBLE_THRESHOLD,
)

DEFAULT_GAP_FRAC = 0.6
_SCALE_FACTORS = (1.0, 0.7, 1.4, 0.85, 1.18, 0.6)
_FONT_CANDIDATES = [
    "arial.ttf", "Arial.ttf", "segoeui.ttf", "calibri.ttf",
    "DejaVuSans.ttf", "LiberationSans-Regular.ttf",
]


def _load_font(size: int):
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _key_offsets(key, stepx: int, stepy: int) -> Tuple[int, int]:
    if key is None:
        return 0, 0
    h = hashlib.sha256(str(key).encode("utf-8")).digest()
    return h[0] % max(1, stepx), h[1] % max(1, stepy)


def _key_angle(key, base_angle: float) -> float:
    """Stamp angle depends on the key (±12° around base). Edge correlation is not
    rotation-invariant, so a wrong key -> wrong angle -> low score."""
    if key is None:
        return base_angle
    h = hashlib.sha256(("angle:" + str(key)).encode("utf-8")).digest()
    return base_angle + (h[2] % 25) - 12


def _render_mask(size, text, key=None, angle=DEFAULT_VISIBLE_ANGLE,
                 font_frac=DEFAULT_VISIBLE_FONT_FRAC, gap_frac=DEFAULT_GAP_FRAC):
    """The visible stamp's ink mask (float 0..1), diagonally tiled over the image.
    Shared by embedding and verification."""
    w, h = size
    fs = max(14, int(min(w, h) * font_frac))
    font = _load_font(fs)

    probe = ImageDraw.Draw(Image.new("L", (8, 8)))
    bbox = probe.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    stepx = tw + int(tw * gap_frac) + 1
    stepy = int(th * 2.6) + 1

    D = int(math.hypot(w, h)) + 2 * max(stepx, stepy)
    layer = Image.new("L", (D, D), 0)
    dl = ImageDraw.Draw(layer)
    ox, oy = _key_offsets(key, stepx, stepy)

    row = 0
    y = -stepy + oy
    while y < D:
        x = -stepx + ox + (stepx // 2 if row % 2 else 0)
        while x < D:
            dl.text((x, y), text, fill=255, font=font)
            x += stepx
        y += stepy
        row += 1

    layer = layer.rotate(_key_angle(key, angle), resample=Image.BICUBIC, expand=False)
    left, top = (D - w) // 2, (D - h) // 2
    layer = layer.crop((left, top, left + w, top + h))
    return np.asarray(layer, dtype=np.float64) / 255.0


def _edge(a: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(a)
    return np.hypot(gx, gy)


def _xcorr_peak(a: np.ndarray, b: np.ndarray) -> float:
    """Peak of normalized cross-correlation over all shifts (via FFT)."""
    a = a - a.mean()
    b = b - b.mean()
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    corr = np.fft.irfft2(np.fft.rfft2(a) * np.conj(np.fft.rfft2(b)), s=a.shape)
    return float(corr.max() / denom)


class VisibleWatermarkLayer(Layer):
    """Human-visible diagonal stamp + blind verification."""

    name_key = "layer.visible.name"

    def embed(self, image: Image.Image, message: str, config) -> EmbedOutcome:
        text = config.visible_text
        if not text:
            return EmbedOutcome(image=image, info={"applied": False})
        opacity = getattr(config, "visible_opacity", DEFAULT_VISIBLE_OPACITY)
        key = config.visible_key if config.visible_key is not None else config.key
        out = self.apply(image, text, key=key, opacity=opacity)
        return EmbedOutcome(image=out, info={"applied": True, "text": text,
                                             "opacity": opacity})

    def extract(self, image: Image.Image, config) -> Optional[LayerResult]:
        # The visible layer carries no secret message; use verify() instead.
        return None

    def apply(self, image: Image.Image, text: str, key=None,
              opacity=DEFAULT_VISIBLE_OPACITY, color=(255, 255, 255),
              angle=DEFAULT_VISIBLE_ANGLE,
              font_frac=DEFAULT_VISIBLE_FONT_FRAC) -> Image.Image:
        base = np.asarray(image.convert("RGB"), dtype=np.float64)
        mask = _render_mask(image.size, text, key=key, angle=angle, font_frac=font_frac)
        a = (mask * opacity)[:, :, None]
        col = np.array(color, dtype=np.float64)[None, None, :]
        out = base * (1.0 - a) + col * a
        return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")

    def verify(self, image: Image.Image, text: str, key=None,
               threshold=DEFAULT_VISIBLE_THRESHOLD, angle=DEFAULT_VISIBLE_ANGLE,
               font_frac=DEFAULT_VISIBLE_FONT_FRAC):
        """Return (present: bool, score: float, info: dict)."""
        img_arr = np.asarray(image.convert("L"), dtype=np.float64)
        img_edge = _edge(img_arr)
        best, best_sf = -1.0, None
        for sf in _SCALE_FACTORS:
            mask = _render_mask(image.size, text, key=key, angle=angle,
                                font_frac=font_frac * sf)
            score = _xcorr_peak(img_edge, _edge(mask))
            if score > best:
                best, best_sf = score, sf
        present = best >= threshold
        info = {"score": round(best, 4), "scale": best_sf,
                "threshold": threshold, "present": present, "text": text}
        return present, best, info


__all__ = ["VisibleWatermarkLayer"]
