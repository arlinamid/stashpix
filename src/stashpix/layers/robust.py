"""Robust DCT watermark layer — JPEG/resize tolerant, carries a 128-bit ID."""

from __future__ import annotations

import io
import uuid
from typing import List, Optional

import numpy as np
from PIL import Image

from ..core.base import Layer, EmbedOutcome, LayerResult
from ..core.imaging import canonical_size
from ..core.keys import derive_seed
from ..core.watermark_frame import (
    COEFS_MID,
    FRAME_BITS,
    build_frame,
    embed_into_Y,
    extract_frames_from_Y,
    extract_from_Y,
    parse_frame,
)
from ..exceptions import SelfVerifyError
from ..registry import Registry

CANON_WIDTH = 512
# Embed-time self-verification: if the freshly written image does not read back,
# retry at a higher strength instead of silently shipping an unreadable mark.
STRENGTH_LADDER = (1.0, 1.35, 1.8, 2.4, 3.2)
MAX_EMBED_ATTEMPTS = len(STRENGTH_LADDER)
# The robustness floor the product promises. Verifying only a clean read-back is
# not enough: on a cover that needs no canonical resize, the base strength can
# pass clean and still be too weak to survive JPEG, which is the whole point of
# this layer. Escalation targets this quality.
VERIFY_JPEG_QUALITY = 50


class RobustWatermarkLayer(Layer):
    """JPEG/resize-tolerant DCT watermark carrying an ID resolved via a registry."""

    name_key = "layer.robust.name"

    def __init__(self, registry: Optional[Registry] = None):
        self.registry = registry or Registry()

    def _render(self, img: Image.Image, frame, seed, method, Q, strength):
        """Write ``frame`` into the image at the canonical scale, full size out."""
        ow, oh = img.size
        cw, ch = canonical_size(ow, oh, CANON_WIDTH)
        work = img.resize((cw, ch), Image.LANCZOS)
        Y, Cb, Cr = [np.array(c, dtype=np.float64) for c in work.convert("YCbCr").split()]
        Y2 = np.clip(embed_into_Y(Y, frame, seed, method, Q, strength, coefs=COEFS_MID),
                     0, 255)
        merged = Image.merge("YCbCr", [Image.fromarray(np.uint8(np.round(c)), "L")
                                       for c in (Y2, Cb, Cr)]).convert("RGB")
        return merged.resize((ow, oh), Image.LANCZOS), (cw, ch)

    def _reads_back(self, image: Image.Image, seed, method, Q, strength,
                    expect: bytes) -> bool:
        """Run the real blind decoder over the rendered image."""
        w, h = image.size
        cw, ch = canonical_size(w, h, CANON_WIDTH)
        work = image.resize((cw, ch), Image.LANCZOS)
        Y = np.array(work.convert("YCbCr").split()[0], dtype=np.float64)
        frame = extract_from_Y(Y, seed, method, Q, strength, coefs=COEFS_MID)
        return parse_frame(frame) == expect

    def _survives_jpeg(self, image: Image.Image, seed, method, Q, strength,
                       expect: bytes, *, quality: int = VERIFY_JPEG_QUALITY) -> bool:
        """Does the mark still read back after a round trip through JPEG?"""
        buf = io.BytesIO()
        image.save(buf, "JPEG", quality=quality)
        buf.seek(0)
        with Image.open(buf) as recoded:
            return self._reads_back(recoded.convert("RGB"), seed, method, Q,
                                    strength, expect)

    def embed(self, image: Image.Image, message: str, config,
              *, source_image: str = "", output_image: str = "") -> EmbedOutcome:
        method = config.robust_method or "jnd"
        Q = config.robust_q
        base_strength = config.robust_strength

        img = image.convert("RGB")
        new_id = uuid.uuid4()
        frame = build_frame(new_id.bytes)
        seed = derive_seed(config.key)

        # The canonical-scale resize round trip and 8-bit quantization are lossy,
        # and how lossy depends entirely on the cover, so no fixed strength works
        # everywhere. Verify what we actually produced and escalate until it both
        # reads back and clears the JPEG floor we promise.
        attempts = []
        best = None          # (image, canon, strength) that at least reads clean
        chosen = None        # the first that also survives JPEG
        for factor in STRENGTH_LADDER:
            strength = base_strength * factor
            rendered, canon = self._render(img, frame, seed, method, Q, strength)
            attempts.append(round(strength, 4))
            if not self._reads_back(rendered, seed, method, Q, strength, new_id.bytes):
                continue
            if best is None:
                best = (rendered, canon, strength)
            if self._survives_jpeg(rendered, seed, method, Q, strength, new_id.bytes):
                chosen = (rendered, canon, strength)
                break

        if best is None:
            raise SelfVerifyError(key="error.robust_self_verify",
                                  detail=f"strengths tried: {attempts}")

        # Fall back to the weakest strength that at least survives a lossless
        # roundtrip. Never ship an unreadable image, but never claim a JPEG
        # guarantee we did not actually verify either.
        jpeg_verified = chosen is not None
        out_full, canon, used_strength = chosen if jpeg_verified else best

        self.registry.add(new_id.hex, message, source_image=source_image,
                          output_image=output_image,
                          meta={"strength": used_strength})

        info = {"id": new_id.hex, "method": method, "canon": canon,
                "strength": used_strength, "attempts": len(attempts),
                "self_verified": True, "jpeg_verified": jpeg_verified}
        if not jpeg_verified:
            info["warning"] = "readable losslessly, but not verified against JPEG"
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
        base = config.robust_strength

        id_bytes = None
        used_method = None
        used_strength = None
        for m in trials:
            # Fixed-Q ignores strength entirely, so it has no ladder to sweep.
            candidates = [base * f for f in STRENGTH_LADDER] if m == "jnd" else [base]
            frames = extract_frames_from_Y(Y, seed, m, config.robust_q, candidates,
                                           coefs=COEFS_MID)
            for strength, frame in zip(candidates, frames):
                # 16-bit sync + 16-bit CRC gate every candidate, so sweeping the
                # ladder buys recall without costing precision.
                parsed = parse_frame(frame)
                if parsed is not None:
                    id_bytes, used_method, used_strength = parsed, m, strength
                    break
            if id_bytes is not None:
                break

        if id_bytes is None:
            return None

        id_hex = uuid.UUID(bytes=id_bytes).hex
        entry = self.registry.get(id_hex)
        info = {"id": id_hex, "method": used_method, "strength": used_strength,
                "in_registry": entry is not None}
        message = entry["message"] if entry else None
        if entry:
            info["entry"] = entry
        return LayerResult(message=message, layer_key=self.name_key, info=info)


__all__ = ["RobustWatermarkLayer", "CANON_WIDTH", "COEFS_MID", "FRAME_BITS"]
