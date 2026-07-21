"""Coding-theory primitives: bit/byte conversions, Hamming(7,4), keystream.

These are pure functions shared mainly by the LSB layer. Reed-Solomon itself is
provided by the ``reedsolo`` package and re-exported here for a single import
point.
"""

from __future__ import annotations

import random
import sys
from typing import List, Sequence

try:
    from reedsolo import RSCodec, ReedSolomonError
except ImportError:  # pragma: no cover - dependency guidance
    print(
        "Missing 'reedsolo'. Install: pip install reedsolo",
        file=sys.stderr,
    )
    raise


# ----------------------------------------------------------------------
# Bit / byte conversions
# ----------------------------------------------------------------------

def bits_to_int(bits: Sequence[int]) -> int:
    return int("".join(str(b) for b in bits), 2) if bits else 0


def int_to_bits(value: int, nbits: int) -> List[int]:
    return [int(b) for b in format(value, f"0{nbits}b")]


def bytes_to_bits(data: bytes) -> List[int]:
    bits: List[int] = []
    for byte in data:
        bits.extend(int(b) for b in format(byte, "08b"))
    return bits


def bits_to_bytes(bits: Sequence[int]) -> bytes:
    n = len(bits) - (len(bits) % 8)
    out = bytearray()
    for i in range(0, n, 8):
        out.append(int("".join(str(b) for b in bits[i:i + 8]), 2))
    return bytes(out)


# ----------------------------------------------------------------------
# Hamming(7,4) — used to protect the small self-describing header
# ----------------------------------------------------------------------

def _hamming74_encode_nibble(bits4: Sequence[int]) -> List[int]:
    d1, d2, d3, d4 = bits4
    p1 = d1 ^ d2 ^ d4
    p2 = d1 ^ d3 ^ d4
    p3 = d2 ^ d3 ^ d4
    return [p1, p2, d1, p3, d2, d3, d4]


def _hamming74_decode_nibble(bits7: Sequence[int]) -> List[int]:
    p1, p2, d1, p3, d2, d3, d4 = bits7
    c1 = p1 ^ d1 ^ d2 ^ d4
    c2 = p2 ^ d1 ^ d3 ^ d4
    c3 = p3 ^ d2 ^ d3 ^ d4
    syndrome = c1 + (c2 << 1) + (c3 << 2)
    corrected = list(bits7)
    if syndrome != 0:
        pos_map = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6}
        idx = pos_map.get(syndrome)
        if idx is not None:
            corrected[idx] ^= 1
    _, _, d1c, _, d2c, d3c, d4c = corrected
    return [d1c, d2c, d3c, d4c]


def hamming_encode_bits(raw_bits: Sequence[int]) -> List[int]:
    bits = list(raw_bits)
    while len(bits) % 4 != 0:
        bits.append(0)
    out: List[int] = []
    for i in range(0, len(bits), 4):
        out.extend(_hamming74_encode_nibble(bits[i:i + 4]))
    return out


def hamming_decode_bits(bits: Sequence[int]) -> List[int]:
    n = len(bits) - (len(bits) % 7)
    out: List[int] = []
    for i in range(0, n, 7):
        out.extend(_hamming74_decode_nibble(bits[i:i + 7]))
    return out


# ----------------------------------------------------------------------
# XOR-whitening keystream — bit i depends only on i (32-bit words)
# ----------------------------------------------------------------------

def keystream_bits(seed, n: int) -> List[int]:
    if n <= 0:
        return []
    rng = random.Random(f"whiten-{seed}")
    bits: List[int] = []
    words = (n + 31) // 32
    for _ in range(words):
        w = rng.getrandbits(32)
        for b in range(32):
            bits.append((w >> b) & 1)
    return bits[:n]


__all__ = [
    "RSCodec",
    "ReedSolomonError",
    "bits_to_int",
    "int_to_bits",
    "bytes_to_bits",
    "bits_to_bytes",
    "hamming_encode_bits",
    "hamming_decode_bits",
    "keystream_bits",
]
