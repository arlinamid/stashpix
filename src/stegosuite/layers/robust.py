"""Robust DCT watermark layer — JPEG/resize tolerant, carries a 128-bit ID.

Embeds an ID into mid-frequency DCT coefficients with perceptually adaptive QIM
(Watson JND) and heavy redundancy + majority voting. The full message is stored
in a :class:`Registry` keyed by the ID.
"""

from __future__ import annotations

import os
import uuid
import random
from typing import List, Optional

import numpy as np
from PIL import Image

from ..core.base import Layer, EmbedOutcome, LayerResult
from ..core.dct import dct2, idct2, qim_embed, qim_extract, block_slack, MIN_DELTA, DC0
from ..core.imaging import canonical_size
from ..core.keys import derive_seed
from ..registry import Registry

CANON_WIDTH = 512
COEFS = [(2, 1), (1, 2), (2, 2), (3, 2), (2, 3)]
SYNC = 0xACED
FRAME_BITS = 160          # 16 sync + 128 id + 16 crc
AC_GATE = 8.0             # block-activity gate: flat/occluded blocks don't vote


# ----------------------------------------------------------------------
# Frame: sync + id + crc
# ----------------------------------------------------------------------

def _int_to_bits_msb(v: int, n: int) -> List[int]:
    return [(v >> i) & 1 for i in range(n - 1, -1, -1)]


def _bits_to_int_msb(bits) -> int:
    v = 0
    for b in bits:
        v = (v << 1) | b
    return v


def _crc16(bits) -> List[int]:
    reg = 0xFFFF
    for b in bits:
        reg ^= (b << 15)
        if reg & 0x8000:
            reg = ((reg << 1) ^ 0x1021) & 0xFFFF
        else:
            reg = (reg << 1) & 0xFFFF
    return [(reg >> i) & 1 for i in range(15, -1, -1)]


def _build_frame(id_bytes16: bytes) -> List[int]:
    id_bits: List[int] = []
    for byte in id_bytes16:
        id_bits.extend(_int_to_bits_msb(byte, 8))
    sync_bits = _int_to_bits_msb(SYNC, 16)
    crc_bits = _crc16(sync_bits + id_bits)
    frame = sync_bits + id_bits + crc_bits
    assert len(frame) == FRAME_BITS
    return frame


def _parse_frame(frame: List[int]) -> Optional[bytes]:
    sync_bits, id_bits, crc_bits = frame[:16], frame[16:144], frame[144:160]
    if _bits_to_int_msb(sync_bits) != SYNC:
        return None
    if _crc16(sync_bits + id_bits) != crc_bits:
        return None
    return bytes(_bits_to_int_msb(id_bits[i:i + 8]) for i in range(0, 128, 8))


def _block_index_map(num_blocks: int, seed):
    rng = random.Random(seed)
    idx = [rng.randrange(FRAME_BITS) for _ in range(num_blocks)]
    wht = [rng.randrange(2) for _ in range(num_blocks)]
    return idx, wht


def _coef_step(coef, slack, cu, cv, method, Q, strength) -> float:
    if method == "jnd":
        return max(MIN_DELTA, strength * slack[cu, cv])
    return Q


def _embed_into_Y(Y, frame, seed, method, Q, strength):
    h, w = Y.shape
    bh, bw = h // 8, w // 8
    idx_map, wht_map = _block_index_map(bh * bw, seed)
    out = Y.copy()
    n = 0
    for by in range(bh):
        for bx in range(bw):
            block = out[by * 8:by * 8 + 8, bx * 8:bx * 8 + 8]
            coef = dct2(block)
            slack = block_slack(coef, DC0) if method == "jnd" else None
            bit = frame[idx_map[n]] ^ wht_map[n]
            for (cu, cv) in COEFS:
                step = _coef_step(coef, slack, cu, cv, method, Q, strength)
                coef[cu, cv] = qim_embed(coef[cu, cv], bit, step)
            out[by * 8:by * 8 + 8, bx * 8:bx * 8 + 8] = idct2(coef)
            n += 1
    return out


def _extract_from_Y(Y, seed, method, Q, strength):
    h, w = Y.shape
    bh, bw = h // 8, w // 8
    idx_map, wht_map = _block_index_map(bh * bw, seed)
    votes0 = [0.0] * FRAME_BITS
    votes1 = [0.0] * FRAME_BITS
    n = 0
    for by in range(bh):
        for bx in range(bw):
            block = Y[by * 8:by * 8 + 8, bx * 8:bx * 8 + 8]
            coef = dct2(block)
            ac_energy = np.sqrt(max(0.0, float((coef ** 2).sum() - coef[0, 0] ** 2)))
            if ac_energy <= AC_GATE:
                n += 1
                continue
            slack = block_slack(coef, DC0) if method == "jnd" else None
            for (cu, cv) in COEFS:
                step = _coef_step(coef, slack, cu, cv, method, Q, strength)
                bit = qim_extract(coef[cu, cv], step) ^ wht_map[n]
                if bit:
                    votes1[idx_map[n]] += 1.0
                else:
                    votes0[idx_map[n]] += 1.0
            n += 1
    return [1 if votes1[i] > votes0[i] else 0 for i in range(FRAME_BITS)]


class RobustWatermarkLayer(Layer):
    """JPEG/resize-tolerant DCT watermark carrying an ID resolved via a registry."""

    name_key = "layer.robust.name"

    def __init__(self, registry: Optional[Registry] = None):
        self.registry = registry or Registry()

    def embed(self, image: Image.Image, message: str, config,
              *, source_image: str = "", output_image: str = "") -> EmbedOutcome:
        method = config.robust_method or "jnd"
        Q = config.robust_q
        strength = config.robust_strength

        img = image.convert("RGB")
        ow, oh = img.size
        cw, ch = canonical_size(ow, oh, CANON_WIDTH)
        work = img.resize((cw, ch), Image.LANCZOS)
        Y, Cb, Cr = [np.array(c, dtype=np.float64) for c in work.convert("YCbCr").split()]

        new_id = uuid.uuid4()
        frame = _build_frame(new_id.bytes)
        seed = derive_seed(config.key)

        Y2 = np.clip(_embed_into_Y(Y, frame, seed, method, Q, strength), 0, 255)
        merged = Image.merge("YCbCr", [Image.fromarray(np.uint8(np.round(c)), "L")
                                       for c in (Y2, Cb, Cr)]).convert("RGB")
        out_full = merged.resize((ow, oh), Image.LANCZOS)

        self.registry.add(new_id.hex, message, source_image=source_image,
                          output_image=output_image)

        info = {"id": new_id.hex, "method": method, "canon": (cw, ch)}
        return EmbedOutcome(image=out_full, info=info)

    def extract(self, image: Image.Image, config) -> Optional[LayerResult]:
        img = image.convert("RGB")
        w, h = img.size
        cw, ch = canonical_size(w, h, CANON_WIDTH)
        work = img.resize((cw, ch), Image.LANCZOS)
        Y = np.array(work.convert("YCbCr").split()[0], dtype=np.float64)
        seed = derive_seed(config.key)

        method = getattr(config, "robust_method", None)
        trials = [method] if method else ["jnd", "qim"]
        id_bytes = None
        used_method = None
        for m in trials:
            frame = _extract_from_Y(Y, seed, m, config.robust_q, config.robust_strength)
            id_bytes = _parse_frame(frame)
            if id_bytes is not None:
                used_method = m
                break

        if id_bytes is None:
            return None

        id_hex = uuid.UUID(bytes=id_bytes).hex
        entry = self.registry.get(id_hex)
        info = {"id": id_hex, "method": used_method, "in_registry": entry is not None}
        message = entry["message"] if entry else None
        if entry:
            info["entry"] = entry
        return LayerResult(message=message, layer_key=self.name_key, info=info)


__all__ = ["RobustWatermarkLayer", "CANON_WIDTH", "COEFS", "FRAME_BITS"]
