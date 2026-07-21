"""StegoEngine — orchestrates all layers into one pipeline with graceful degradation.

Embed order: visible watermark -> robust DCT watermark -> LSB (the visible/robust
output becomes the cover for the LSB, so the invisible layers don't interfere).

Extract order: LSB (full message, lossless) -> robust ID + registry (survives
JPEG/resize). Optionally geometric (SIFT) re-sync for images placed into another
image and/or partially occluded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from PIL import Image

from .config import EmbedConfig, ExtractConfig, VerifyConfig
from .core.imaging import open_rgb, assert_lossless, save_lossless
from .exceptions import StegoError
from .i18n import t
from .layers import (
    LsbLayer,
    RobustWatermarkLayer,
    VisibleWatermarkLayer,
    GeometricSynchronizer,
)
from .registry import Registry


@dataclass
class EmbedResult:
    output_path: str
    robust_id: Optional[str] = None
    info: Dict[str, Any] = field(default_factory=dict)


class StegoEngine:
    """High-level facade over the individual steganography layers."""

    def __init__(self, registry: Optional[Registry] = None):
        self.registry = registry or Registry()
        self.visible = VisibleWatermarkLayer()
        self.robust = RobustWatermarkLayer(self.registry)
        self.lsb = LsbLayer()
        self.geometry = GeometricSynchronizer()

    # ------------------------------------------------------------------ embed
    def embed(self, image: Image.Image, message: str, config: EmbedConfig,
              *, source_image: str = "", output_image: str = "") -> Tuple[Image.Image, Dict[str, Any]]:
        """Embed all enabled layers into an in-memory image."""
        if not message and (config.enable_lsb or config.enable_robust):
            raise StegoError(key="error.no_message")

        img = image.convert("RGB")
        info: Dict[str, Any] = {"layers": []}

        if config.visible_text:
            outcome = self.visible.embed(img, message, config)
            img = outcome.image
            info["visible"] = outcome.info
            info["layers"].append("visible")

        if config.enable_robust:
            outcome = self.robust.embed(img, message, config,
                                        source_image=source_image,
                                        output_image=output_image)
            img = outcome.image
            info["robust"] = outcome.info
            info["robust_id"] = outcome.info.get("id")
            info["layers"].append("robust")

        if config.enable_lsb:
            outcome = self.lsb.embed(img, message, config)
            img = outcome.image
            info["lsb"] = outcome.info
            info["layers"].append("lsb")

        # Store a reference copy of the final stego so a later extraction can
        # auto-match it (SIFT) even when only a rotated/occluded PART of it
        # appears inside another image — no manual reference needed.
        if config.enable_robust and info.get("robust_id") and self.geometry.available:
            try:
                self.registry.save_reference(info["robust_id"], img)
            except OSError:
                pass

        return img, info

    def embed_file(self, image_path: str, message: str, output_path: str,
                   config: Optional[EmbedConfig] = None) -> EmbedResult:
        config = config or EmbedConfig()
        img = Image.open(image_path)
        if config.enable_lsb:
            assert_lossless(img, image_path, "input")
        img = img.convert("RGB")

        out_name = os.path.basename(output_path)
        result_img, info = self.embed(
            img, message, config,
            source_image=os.path.basename(image_path),
            output_image=out_name,
        )
        saved = save_lossless(result_img, output_path)
        return EmbedResult(output_path=saved, robust_id=info.get("robust_id"), info=info)

    # ---------------------------------------------------------------- extract
    def extract(self, image: Image.Image, config: ExtractConfig
                ) -> Tuple[Optional[str], Dict[str, Any]]:
        """Graceful degradation: LSB first, then robust ID + registry."""
        img = image.convert("RGB")
        info: Dict[str, Any] = {"layer": None}

        # 1) LSB — full message if the image is lossless
        try:
            result = self.lsb.extract(img, config)
            if result is not None:
                info["layer"] = t("layer.lsb.name")
                info["layer_key"] = "lsb"
                info["lsb_info"] = result.info
                return result.message, info
        except StegoError as e:
            info["lsb_failed"] = str(e)

        # 2) Robust ID -> registry (survives JPEG/resize)
        result = self.robust.extract(img, config)
        if result is not None:
            info["robust_info"] = result.info
            info["robust_id"] = result.info.get("id")
            if result.message is not None:
                info["layer"] = t("layer.robust.name")
                info["layer_key"] = "robust"
                return result.message, info

        # 3) Reference-free geometric recovery (deskew/crop + orientation probe).
        #    Handles rotated / reframed / partially occluded images without a
        #    reference, as long as the watermarked patch is textured.
        if getattr(config, "blind_geo", True) and self.geometry.available:
            msg = self._blind_extract(img, config, info)
            if msg is not None:
                return msg, info

            # 4) Auto-match against every registered reference (SIFT). Recovers a
            #    rotated/occluded SUB-IMAGE of one of our stego images with no
            #    manual reference — the registry acts as an image index.
            msg = self._registry_geo_extract(img, config, info)
            if msg is not None:
                return msg, info

        return None, info

    def _registry_geo_extract(self, img: Image.Image, config: ExtractConfig,
                              info: Dict[str, Any]) -> Optional[str]:
        entries = self.registry.all()
        try:
            recv_rgb, k1, d1 = self.geometry.features(img)
        except StegoError as e:
            info["auto_ref"] = {"used": True, "error": str(e)}
            return None
        scanned = 0
        best = {"inliers": 0}
        for id_hex in entries:
            ref_path = self.registry.reference_path(id_hex)
            if not ref_path:
                continue
            scanned += 1
            ref = open_rgb(ref_path)
            warped, stat = self.geometry.warp_with_features(recv_rgb, k1, d1, ref)
            if stat.get("inliers", 0) > best["inliers"]:
                best = {"id": id_hex, **stat}
            if warped is None:
                continue
            result = self.robust.extract(warped, config)
            if result is not None and result.message is not None:
                info["auto_ref"] = {"used": True, "scanned": scanned,
                                    "matched": id_hex, **stat}
                info["layer"] = t("layer.robust.name")
                info["layer_key"] = "robust"
                info["robust_info"] = result.info
                info["robust_id"] = result.info.get("id")
                return result.message
        info["auto_ref"] = {"used": True, "scanned": scanned, "matched": None,
                            "best": best}
        return None

    def _blind_extract(self, img: Image.Image, config: ExtractConfig,
                       info: Dict[str, Any]) -> Optional[str]:
        try:
            candidates, stat = self.geometry.blind_candidates(img)
        except StegoError as e:
            info["blind_geo"] = {"used": True, "error": str(e)}
            return None
        info["blind_geo"] = {"used": True, "candidates": len(candidates), **stat}
        for idx, cand in enumerate(candidates):
            result = self.robust.extract(cand, config)
            if result is not None and result.message is not None:
                info["layer"] = t("layer.robust.name")
                info["layer_key"] = "robust"
                info["robust_info"] = result.info
                info["robust_id"] = result.info.get("id")
                info["blind_geo"]["orientation"] = idx
                return result.message
        return None

    def extract_file(self, image_path: str, config: Optional[ExtractConfig] = None
                     ) -> Tuple[Optional[str], Dict[str, Any]]:
        config = config or ExtractConfig()
        return self.extract(open_rgb(image_path), config)

    def extract_geo(self, recv: Image.Image, ref: Image.Image,
                    config: Optional[ExtractConfig] = None
                    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """Geometry-tolerant extraction against a user-supplied reference image.

        Tries the normal graceful-degradation path first, then SIFT-warps the
        received image onto ``ref`` and reads the robust watermark from there.
        """
        config = config or ExtractConfig()
        recv = recv.convert("RGB")

        msg, info = self.extract(recv, config)
        info.setdefault("geo", {})["used"] = False
        if msg is not None:
            return msg, info

        warped, stat = self.geometry.warp_to_reference(recv, ref.convert("RGB"))
        info["geo"] = {"used": True, "registered": warped is not None, **stat}
        if warped is None:
            return None, info

        result = self.robust.extract(warped, config)
        if result is not None and result.message is not None:
            info["layer"] = t("layer.robust.name")
            info["layer_key"] = "robust"
            info["robust_info"] = result.info
            info["robust_id"] = result.info.get("id")
            return result.message, info
        return None, info

    def extract_geo_file(self, image_path: str, reference_path: str,
                         config: Optional[ExtractConfig] = None
                         ) -> Tuple[Optional[str], Dict[str, Any]]:
        """Geometry-tolerant extraction: try direct, then SIFT-warp to reference."""
        return self.extract_geo(open_rgb(image_path), open_rgb(reference_path), config)

    # ----------------------------------------------------------------- verify
    def verify_visible(self, image: Image.Image, config: VerifyConfig):
        """Return (present, score, info) for a visible watermark."""
        return self.visible.verify(image, config.text, key=config.key,
                                   threshold=config.threshold)

    def verify_visible_file(self, image_path: str, config: VerifyConfig):
        return self.verify_visible(open_rgb(image_path), config)


__all__ = ["StegoEngine", "EmbedResult"]
