"""Image IO helpers: format checks, loading, lossless saving, canonical resize.

Centralizes the "is this format safe for hidden data?" logic and the extension
coercion so layers and the engine never duplicate it.
"""

from __future__ import annotations

import os
from typing import Tuple

from PIL import Image

from ..exceptions import LossyFormatError

LOSSLESS_FORMATS = {"PNG", "BMP", "TIFF"}
LOSSLESS_EXTS = (".png", ".bmp", ".tiff", ".tif")


def open_rgb(path: str) -> Image.Image:
    """Open an image as RGB (accepts any format — used for extraction)."""
    return Image.open(path).convert("RGB")


def assert_lossless(img: Image.Image, path: str, role: str) -> None:
    """Raise :class:`LossyFormatError` if the image/path is a lossy format.

    Used for LSB, whose data lives in the spatial LSBs and would be destroyed by
    JPEG or any lossy codec.
    """
    fmt = (img.format or "").upper()
    ext = os.path.splitext(path)[1].lower()
    if fmt and fmt not in LOSSLESS_FORMATS:
        raise LossyFormatError(path=path, role=role, fmt=fmt)
    if ext in (".jpg", ".jpeg"):
        raise LossyFormatError(key="error.lossy_ext", path=path)


def coerce_lossless_path(path: str) -> str:
    """Force a lossless extension; default to .png if the extension is lossy."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in LOSSLESS_EXTS:
        return os.path.splitext(path)[0] + ".png"
    return path


def save_lossless(img: Image.Image, path: str) -> str:
    """Save ``img`` losslessly, coercing the extension if needed. Returns path."""
    path = coerce_lossless_path(path)
    img.save(path)
    return path


def canonical_size(w: int, h: int, canon_width: int) -> Tuple[int, int]:
    """8-aligned canonical size preserving aspect ratio (for DCT sync)."""
    cw = 8 * round(canon_width / 8)
    ch = 8 * max(1, round(canon_width * h / w / 8))
    return cw, ch


__all__ = [
    "LOSSLESS_FORMATS",
    "LOSSLESS_EXTS",
    "open_rgb",
    "assert_lossless",
    "coerce_lossless_path",
    "save_lossless",
    "canonical_size",
]
