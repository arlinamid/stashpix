"""Shared DCT watermark frame codec and Y-channel embed/extract primitives."""

from __future__ import annotations

import random
import uuid
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .coding import hamming_encode_bits, hamming_decode_bits
from .dct import dct2, idct2, qim_embed, qim_extract, block_slack, MIN_DELTA, DC0

COEFS_MID = [(2, 1), (1, 2), (2, 2), (3, 2), (2, 3)]
SYNC = 0xACED
RAW_FRAME_BITS = 160                              # sync(16) + id(128) + crc(16)
FRAME_BITS = ((RAW_FRAME_BITS + 3) // 4) * 7       # Hamming(7,4) on-wire length (280)
AC_GATE = 8.0
# Per-block JND scale ramps from 0 at AC_GATE to 1 at TEXTURE_FULL (flat sky → skip).
TEXTURE_FULL = 64.0
TileBounds = Optional[Tuple[int, int, int, int]]  # y0, x0, y1, x1 pixel coords


def _block_ac_energy(coef: np.ndarray) -> float:
    return float(np.sqrt(max(0.0, float((coef ** 2).sum() - coef[0, 0] ** 2))))


def adaptive_strength_scale(ac_energy: float) -> float:
    """Map block AC energy to a 0..1 JND strength multiplier (embed + extract).

    Flat blocks (sky, smooth gradients) get scale 0 — no embed, no votes —
    matching the extract AC gate and avoiding a visible 8×8 grid where the
    watermark cannot help decoding anyway.
    """
    if ac_energy <= AC_GATE:
        return 0.0
    if ac_energy >= TEXTURE_FULL:
        return 1.0
    return (ac_energy - AC_GATE) / (TEXTURE_FULL - AC_GATE)


def int_to_bits_msb(v: int, n: int) -> List[int]:
    return [(v >> i) & 1 for i in range(n - 1, -1, -1)]


def bits_to_int_msb(bits) -> int:
    v = 0
    for b in bits:
        v = (v << 1) | b
    return v


def crc16(bits) -> List[int]:
    reg = 0xFFFF
    for b in bits:
        reg ^= (b << 15)
        if reg & 0x8000:
            reg = ((reg << 1) ^ 0x1021) & 0xFFFF
        else:
            reg = (reg << 1) & 0xFFFF
    return [(reg >> i) & 1 for i in range(15, -1, -1)]


def build_frame(id_bytes16: bytes) -> List[int]:
    """Build sync+id+crc (160 bits), then Hamming(7,4)-encode to 280 bits.

    A single flipped bit after mild attack / geo realignment is corrected
    instead of failing the CRC outright.
    """
    id_bits: List[int] = []
    for byte in id_bytes16:
        id_bits.extend(int_to_bits_msb(byte, 8))
    sync_bits = int_to_bits_msb(SYNC, 16)
    crc_bits = crc16(sync_bits + id_bits)
    raw = sync_bits + id_bits + crc_bits
    assert len(raw) == RAW_FRAME_BITS
    frame = hamming_encode_bits(raw)
    assert len(frame) == FRAME_BITS
    return frame


def parse_frame(frame: List[int]) -> Optional[bytes]:
    raw = hamming_decode_bits(frame)[:RAW_FRAME_BITS]
    sync_bits, id_bits, crc_bits = raw[:16], raw[16:144], raw[144:160]
    if bits_to_int_msb(sync_bits) != SYNC:
        return None
    if crc16(sync_bits + id_bits) != crc_bits:
        return None
    return bytes(bits_to_int_msb(id_bits[i:i + 8]) for i in range(0, 128, 8))


def frame_from_id_hex(id_hex: str) -> List[int]:
    return build_frame(uuid.UUID(hex=id_hex).bytes)


def _block_index_map(num_blocks: int, seed, *, salt: str = "") -> Tuple[List[int], List[int]]:
    rng = random.Random(f"{seed}:{salt}")
    idx = [rng.randrange(FRAME_BITS) for _ in range(num_blocks)]
    wht = [rng.randrange(2) for _ in range(num_blocks)]
    return idx, wht


def _coef_step(coef, slack, cu, cv, method, Q, strength, *,
               ac_energy: float = TEXTURE_FULL, auto_adapt: bool = True) -> float:
    if method == "jnd":
        eff = strength
        if auto_adapt:
            eff *= adaptive_strength_scale(ac_energy)
        return max(MIN_DELTA, eff * slack[cu, cv])
    return Q


def _block_in_tile(by: int, bx: int, tile: TileBounds) -> bool:
    if tile is None:
        return True
    y0, x0, y1, x1 = tile
    py0, px0 = by * 8, bx * 8
    py1, px1 = py0 + 8, px0 + 8
    return py0 < y1 and py1 > y0 and px0 < x1 and px1 > x0


def embed_into_Y(Y, frame, seed, method, Q, strength, *,
                 coefs: Sequence[Tuple[int, int]] = COEFS_MID,
                 tile: TileBounds = None, salt: str = "",
                 auto_adapt: bool = True) -> np.ndarray:
    h, w = Y.shape
    bh, bw = h // 8, w // 8
    blocks = [(by, bx) for by in range(bh) for bx in range(bw)
              if _block_in_tile(by, bx, tile)]
    idx_map, wht_map = _block_index_map(len(blocks), seed, salt=salt)
    out = Y.copy()
    for n, (by, bx) in enumerate(blocks):
        block = out[by * 8:by * 8 + 8, bx * 8:bx * 8 + 8]
        coef = dct2(block)
        ac_energy = _block_ac_energy(coef)
        if auto_adapt and adaptive_strength_scale(ac_energy) <= 0.0:
            continue
        slack = block_slack(coef, DC0) if method == "jnd" else None
        bit = frame[idx_map[n]] ^ wht_map[n]
        for cu, cv in coefs:
            step = _coef_step(coef, slack, cu, cv, method, Q, strength,
                               ac_energy=ac_energy, auto_adapt=auto_adapt)
            coef[cu, cv] = qim_embed(coef[cu, cv], bit, step)
        out[by * 8:by * 8 + 8, bx * 8:bx * 8 + 8] = idct2(coef)
    return out


def extract_from_Y(Y, seed, method, Q, strength, *,
                     coefs: Sequence[Tuple[int, int]] = COEFS_MID,
                     tile: TileBounds = None, salt: str = "",
                     auto_adapt: bool = True) -> List[int]:
    h, w = Y.shape
    bh, bw = h // 8, w // 8
    blocks = [(by, bx) for by in range(bh) for bx in range(bw)
              if _block_in_tile(by, bx, tile)]
    idx_map, wht_map = _block_index_map(len(blocks), seed, salt=salt)
    votes0 = [0.0] * FRAME_BITS
    votes1 = [0.0] * FRAME_BITS
    for n, (by, bx) in enumerate(blocks):
        block = Y[by * 8:by * 8 + 8, bx * 8:bx * 8 + 8]
        coef = dct2(block)
        ac_energy = _block_ac_energy(coef)
        if ac_energy <= AC_GATE:
            continue
        slack = block_slack(coef, DC0) if method == "jnd" else None
        for cu, cv in coefs:
            step = _coef_step(coef, slack, cu, cv, method, Q, strength,
                               ac_energy=ac_energy, auto_adapt=auto_adapt)
            bit = qim_extract(coef[cu, cv], step) ^ wht_map[n]
            if bit:
                votes1[idx_map[n]] += 1.0
            else:
                votes0[idx_map[n]] += 1.0
    return [1 if votes1[i] > votes0[i] else 0 for i in range(FRAME_BITS)]


def merge_frame_votes(frames: Sequence[List[int]]) -> List[int]:
    if not frames:
        return [0] * FRAME_BITS
    votes0 = [0.0] * FRAME_BITS
    votes1 = [0.0] * FRAME_BITS
    for frame in frames:
        for i, bit in enumerate(frame):
            if bit:
                votes1[i] += 1.0
            else:
                votes0[i] += 1.0
    return [1 if votes1[i] > votes0[i] else 0 for i in range(FRAME_BITS)]


__all__ = [
    "COEFS_MID",
    "SYNC",
    "RAW_FRAME_BITS",
    "FRAME_BITS",
    "AC_GATE",
    "TEXTURE_FULL",
    "adaptive_strength_scale",
    "build_frame",
    "parse_frame",
    "frame_from_id_hex",
    "embed_into_Y",
    "extract_from_Y",
    "merge_frame_votes",
]
