"""Shared DCT watermark frame codec and Y-channel embed/extract primitives."""

from __future__ import annotations

import random
import uuid
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .coding import hamming_encode_bits, hamming_decode_bits
from .dct import (
    dct2,
    idct2,
    qim_embed,
    qim_extract,
    qim_confidence,
    luminance_slack,
    CM_W,
    MIN_DELTA,
    DC0,
)

COEFS_MID = [(2, 1), (1, 2), (2, 2), (3, 2), (2, 3)]
SYNC = 0xACED
RAW_FRAME_BITS = 160                              # sync(16) + id(128) + crc(16)
FRAME_BITS = ((RAW_FRAME_BITS + 3) // 4) * 7       # Hamming(7,4) on-wire length (280)
AC_GATE = 8.0
# Per-block texture scale: 0 at AC_GATE (flat sky → skip), 1 at TEXTURE_FULL,
# then grows with Watson's contrast-masking exponent up to MAX_SCALE.
TEXTURE_FULL = 64.0
MAX_SCALE = 4.0
TileBounds = Optional[Tuple[int, int, int, int]]  # y0, x0, y1, x1 pixel coords


def block_ac_energy(coef: np.ndarray,
                    coefs: Sequence[Tuple[int, int]] = COEFS_MID) -> float:
    """AC energy of an 8x8 block, EXCLUDING DC and the carrier coefficients.

    Excluding the carriers is what makes the measure survive embedding: the
    encoder sees the clean block, the decoder sees the watermarked one, and both
    must derive the same QIM step. Since ``coefs`` are the only cells QIM
    touches, leaving them out of the sum makes the two agree.
    """
    total = float((coef ** 2).sum()) - float(coef[0, 0]) ** 2
    for cu, cv in coefs:
        total -= float(coef[cu, cv]) ** 2
    return float(np.sqrt(max(0.0, total)))


def adaptive_strength_scale(ac_energy: float) -> float:
    """Map embed-invariant block AC energy to a JND strength multiplier.

    Flat blocks (sky, smooth gradients) get 0 — no embed, no votes — which both
    matches the decoder's AC gate and avoids a visible 8x8 grid where the
    watermark could not survive anyway. Above ``TEXTURE_FULL`` the scale keeps
    growing with texture (contrast masking), recovering the robustness that
    dropping Watson's per-coefficient self-masking term would otherwise cost.

    KNOWN LIMIT: just above the gate the scale approaches 0, so the step becomes
    tiny and the few percent of energy drift from the canonical resize round
    trip moves it by ~100%. Those blocks are the tail of the step-drift
    distribution (measured: median 5.75%, worst ~57%). Flooring the ramp at a
    usable minimum would stabilise them, but it also raises the modulation
    energy in near-flat blocks, which risks the visible 8x8 grid this gate
    exists to prevent. Needs a PSNR + attack sweep before changing -- see the
    follow-up note in the PR.
    """
    if ac_energy <= AC_GATE:
        return 0.0
    if ac_energy < TEXTURE_FULL:
        return (ac_energy - AC_GATE) / (TEXTURE_FULL - AC_GATE)
    return min(MAX_SCALE, (ac_energy / TEXTURE_FULL) ** CM_W)


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


def block_steps(coef: np.ndarray, method: str, Q: float, strength: float,
                coefs: Sequence[Tuple[int, int]] = COEFS_MID):
    """QIM step per carrier coefficient, plus the block's texture scale.

    Every input is embed-invariant (DC + non-carrier AC energy), so the encoder
    and the blind decoder derive identical steps from their respective images.
    Returns ``(steps_by_coef, scale)``; ``scale == 0`` means "skip this block".
    """
    scale, t_lum = block_profile(coef, method, coefs)
    if method != "jnd":
        return {cc: Q for cc in coefs}, scale
    if scale <= 0.0:
        return {}, 0.0
    eff = strength * scale
    return {(cu, cv): max(MIN_DELTA, eff * t_lum[cu, cv]) for cu, cv in coefs}, scale


def block_profile(coef: np.ndarray, method: str,
                  coefs: Sequence[Tuple[int, int]] = COEFS_MID):
    """Strength-independent part of the step computation.

    Returns ``(scale, t_lum)``. ``scale == 0`` means "skip this block". Split out
    from the strength so the decoder can sweep several candidate strengths over a
    single DCT pass instead of redoing the transform for each.
    """
    if method != "jnd":
        return 1.0, None
    scale = adaptive_strength_scale(block_ac_energy(coef, coefs))
    if scale <= 0.0:
        return 0.0, None
    return scale, luminance_slack(coef, DC0)


def _block_in_tile(by: int, bx: int, tile: TileBounds) -> bool:
    if tile is None:
        return True
    y0, x0, y1, x1 = tile
    py0, px0 = by * 8, bx * 8
    py1, px1 = py0 + 8, px0 + 8
    return py0 < y1 and py1 > y0 and px0 < x1 and px1 > x0


def embed_into_Y(Y, frame, seed, method, Q, strength, *,
                 coefs: Sequence[Tuple[int, int]] = COEFS_MID,
                 tile: TileBounds = None, salt: str = "") -> np.ndarray:
    h, w = Y.shape
    bh, bw = h // 8, w // 8
    blocks = [(by, bx) for by in range(bh) for bx in range(bw)
              if _block_in_tile(by, bx, tile)]
    idx_map, wht_map = _block_index_map(len(blocks), seed, salt=salt)
    out = Y.copy()
    for n, (by, bx) in enumerate(blocks):
        block = out[by * 8:by * 8 + 8, bx * 8:bx * 8 + 8]
        coef = dct2(block)
        steps, scale = block_steps(coef, method, Q, strength, coefs)
        if scale <= 0.0:
            continue
        bit = frame[idx_map[n]] ^ wht_map[n]
        for cu, cv in coefs:
            coef[cu, cv] = qim_embed(coef[cu, cv], bit, steps[(cu, cv)])
        out[by * 8:by * 8 + 8, bx * 8:bx * 8 + 8] = idct2(coef)
    return out


def extract_frames_from_Y(Y, seed, method, Q, strengths: Sequence[float], *,
                          coefs: Sequence[Tuple[int, int]] = COEFS_MID,
                          tile: TileBounds = None,
                          salt: str = "") -> List[List[int]]:
    """Blind frame read for several candidate strengths in one DCT pass.

    Each carrier coefficient contributes a vote weighted by how cleanly it sits
    on the QIM lattice, so a block degraded by JPEG or resampling dilutes its own
    vote instead of outvoting an intact block.

    The encoder may have escalated its strength to make the mark survive (see
    ``layers.robust``), and the step scales linearly with it, so the decoder has
    to try each candidate. Only the cheap per-strength arithmetic is repeated --
    the transform and the perceptual profile are computed once per block.
    """
    h, w = Y.shape
    bh, bw = h // 8, w // 8
    blocks = [(by, bx) for by in range(bh) for bx in range(bw)
              if _block_in_tile(by, bx, tile)]
    idx_map, wht_map = _block_index_map(len(blocks), seed, salt=salt)
    votes0 = [[0.0] * FRAME_BITS for _ in strengths]
    votes1 = [[0.0] * FRAME_BITS for _ in strengths]

    for n, (by, bx) in enumerate(blocks):
        coef = dct2(Y[by * 8:by * 8 + 8, bx * 8:bx * 8 + 8])
        scale, t_lum = block_profile(coef, method, coefs)
        if scale <= 0.0:
            continue
        target = idx_map[n]
        whiten = wht_map[n]
        for si, strength in enumerate(strengths):
            eff = strength * scale
            for cu, cv in coefs:
                step = Q if method != "jnd" else max(MIN_DELTA, eff * t_lum[cu, cv])
                c = coef[cu, cv]
                weight = qim_confidence(c, step)
                if weight <= 0.0:
                    continue
                if qim_extract(c, step) ^ whiten:
                    votes1[si][target] += weight
                else:
                    votes0[si][target] += weight

    return [[1 if votes1[si][i] > votes0[si][i] else 0 for i in range(FRAME_BITS)]
            for si in range(len(strengths))]


def extract_from_Y(Y, seed, method, Q, strength, *,
                     coefs: Sequence[Tuple[int, int]] = COEFS_MID,
                     tile: TileBounds = None, salt: str = "") -> List[int]:
    """Single-strength blind frame read."""
    return extract_frames_from_Y(Y, seed, method, Q, [strength],
                                 coefs=coefs, tile=tile, salt=salt)[0]


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
    "MAX_SCALE",
    "adaptive_strength_scale",
    "block_ac_energy",
    "block_profile",
    "block_steps",
    "extract_frames_from_Y",
    "build_frame",
    "parse_frame",
    "frame_from_id_hex",
    "embed_into_Y",
    "extract_from_Y",
    "merge_frame_votes",
]
