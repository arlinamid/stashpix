"""Shared geometric-attack helpers for geo / morph tests."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


def require_cv2():
    if cv2 is None:
        import pytest
        pytest.skip("opencv-python required for geometric tests")


def to_bgr(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)


def to_pil(bgr: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def swirl(img: Image.Image, strength: float = 0.6) -> Image.Image:
    require_cv2()
    bgr = to_bgr(img)
    h, w = bgr.shape[:2]
    cx, cy = w / 2.0, h / 2.0
    xx, yy = np.meshgrid(np.arange(w), np.arange(h))
    dx, dy = xx - cx, yy - cy
    r = np.sqrt(dx * dx + dy * dy)
    ang = np.arctan2(dy, dx) + strength * np.exp(-r / (0.5 * min(w, h)))
    mapx = (cx + r * np.cos(ang)).astype(np.float32)
    mapy = (cy + r * np.sin(ang)).astype(np.float32)
    out = cv2.remap(bgr, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return to_pil(out)


def wave(img: Image.Image, amp: float = 4.0) -> Image.Image:
    require_cv2()
    bgr = to_bgr(img)
    h, w = bgr.shape[:2]
    xx, yy = np.meshgrid(np.arange(w), np.arange(h))
    mapx = (xx + amp * np.sin(2 * np.pi * yy / 180.0)).astype(np.float32)
    mapy = (yy + amp * np.sin(2 * np.pi * xx / 180.0)).astype(np.float32)
    out = cv2.remap(bgr, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return to_pil(out)


def elastic(img: Image.Image, amp: float = 8.0) -> Image.Image:
    require_cv2()
    bgr = to_bgr(img)
    h, w = bgr.shape[:2]
    small = np.random.RandomState(7).randn(8, 8).astype(np.float32)
    field = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC) * amp
    xx, yy = np.meshgrid(np.arange(w), np.arange(h))
    mapx = (xx + field).astype(np.float32)
    mapy = (yy + field * 0.9).astype(np.float32)
    out = cv2.remap(bgr, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return to_pil(out)


def perspective(img: Image.Image, amt: float = 0.1) -> Image.Image:
    require_cv2()
    bgr = to_bgr(img)
    h, w = bgr.shape[:2]
    d = amt * min(w, h)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[d, d * 0.5], [w - d * 0.7, d], [w - d, h - d * 0.6], [d * 0.6, h - d]])
    M = cv2.getPerspectiveTransform(src, dst)
    out = cv2.warpPerspective(bgr, M, (w, h), borderMode=cv2.BORDER_REFLECT)
    return to_pil(out)


def place_on_green(patch: Image.Image, occlude_frac: float = 0.0,
                   pad: int = 40) -> Image.Image:
    """Paste ``patch`` onto a green canvas; optionally cover the left fraction."""
    nw, nh = patch.size
    canvas = Image.new("RGB", (nw + 2 * pad, nh + 2 * pad), (0, 180, 0))
    ox, oy = pad, pad
    canvas.paste(patch, (ox, oy))
    if occlude_frac > 0:
        draw = ImageDraw.Draw(canvas)
        cover_w = int(nw * occlude_frac)
        draw.rectangle([ox - 8, oy - 8, ox + cover_w, oy + nh + 8], fill=(20, 20, 20))
    return canvas
