"""Robust DCT watermark layer — JPEG/resize tolerant, carries a 128-bit ID."""

from __future__ import annotations

import uuid
from typing import List, Optional

import numpy as np
from PIL import Image

from ..core.base import Layer, EmbedOutcome, LayerResult
from ..core.imaging import canonical_size
from ..core.keys import derive_seed, embed_key_tag
from ..core.watermark_frame import (
    COEFS_MID,
    FRAME_BITS,
    build_frame,
    embed_into_Y,
    extract_from_Y,
    parse_frame,
)
from ..registry import Registry

CANON_WIDTH = 512


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
        frame = build_frame(new_id.bytes)
        seed = derive_seed(config.key)

        Y2 = np.clip(embed_into_Y(Y, frame, seed, method, Q, strength, coefs=COEFS_MID,
                                   auto_adapt=config.robust_auto_adapt),
                     0, 255)
        merged = Image.merge("YCbCr", [Image.fromarray(np.uint8(np.round(c)), "L")
                                       for c in (Y2, Cb, Cr)]).convert("RGB")
        out_full = merged.resize((ow, oh), Image.LANCZOS)

        self.registry.add(new_id.hex, message, source_image=source_image,
                          output_image=output_image,
                          meta={"key_tag": embed_key_tag(config.key)})

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
            frame = extract_from_Y(Y, seed, m, config.robust_q, config.robust_strength,
                                   coefs=COEFS_MID, auto_adapt=config.robust_auto_adapt)
            id_bytes = parse_frame(frame)
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


__all__ = ["RobustWatermarkLayer", "CANON_WIDTH", "COEFS_MID", "FRAME_BITS"]
