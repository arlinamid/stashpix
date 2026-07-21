"""Perceptual hashes (dHash / pHash) for reference shortlisting."""

from __future__ import annotations

import numpy as np
from PIL import Image


def _to_gray_small(img: Image.Image, size: tuple[int, int]) -> np.ndarray:
    return np.asarray(img.convert("L").resize(size, Image.Resampling.LANCZOS), dtype=np.float32)


def dhash_hex(img: Image.Image, *, hash_size: int = 8) -> str:
    """Difference hash — 64-bit default, returned as 16 hex chars."""
    gray = _to_gray_small(img, (hash_size + 1, hash_size))
    diff = gray[:, 1:] > gray[:, :-1]
    bits = diff.flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    width = hash_size * hash_size
    return f"{value:0{width // 4}x}"


def phash_hex(img: Image.Image, *, hash_size: int = 8) -> str:
    """Simple DCT-based pHash — 64-bit default."""
    gray = _to_gray_small(img, (hash_size * 4, hash_size * 4))
    try:
        import cv2

        dct = cv2.dct(gray)
        low = dct[:hash_size, :hash_size]
        flat = low.flatten()
        med = np.median(flat[1:])
        bits = flat > med
    except ImportError:
        # Fallback when OpenCV is absent: coarse grid average hash
        block = gray.reshape(hash_size, 4, hash_size, 4).mean(axis=(1, 3))
        med = np.median(block)
        bits = (block > med).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    width = hash_size * hash_size
    return f"{value:0{width // 4}x}"


def hamming_hex(a: str, b: str) -> int:
    """Hamming distance between equal-length hex hash strings."""
    if len(a) != len(b):
        return max(len(a), len(b)) * 4
    ai = int(a, 16)
    bi = int(b, 16)
    x = ai ^ bi
    return x.bit_count()


__all__ = ["dhash_hex", "phash_hex", "hamming_hex"]
