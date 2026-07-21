"""Geometric synchronizer — SIFT + homography re-alignment.

If a watermarked image was placed into another image (translated/scaled/rotated)
and/or partially occluded, this warps the received image back onto the reference
(the registered/encoded image) so the DCT watermark grid lines up again.

OpenCV is an optional dependency; :class:`GeometricSynchronizer.available`
reports whether it can be used.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
from PIL import Image

from ..exceptions import DependencyError

try:
    import cv2
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None


class GeometricSynchronizer:
    """Re-aligns a received image to a reference via SIFT feature matching."""

    def __init__(self, min_matches: int = 15, ratio: float = 0.75,
                 ransac_thresh: float = 5.0):
        self.min_matches = min_matches
        self.ratio = ratio
        self.ransac_thresh = ransac_thresh

    @property
    def available(self) -> bool:
        return cv2 is not None

    def features(self, img: Image.Image):
        """Compute SIFT keypoints/descriptors once (for reuse across references)."""
        if cv2 is None:
            raise DependencyError(key="error.dependency_cv2")
        rgb = np.asarray(img.convert("RGB"))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        k, d = cv2.SIFT_create().detectAndCompute(gray, None)
        return rgb, k, d

    def warp_with_features(self, recv_rgb, k1, d1, ref: Image.Image
                           ) -> Tuple[Optional[Image.Image], dict]:
        """Warp a suspect (given its precomputed features) onto ``ref``."""
        if cv2 is None:
            raise DependencyError(key="error.dependency_cv2")
        ref_rgb = np.asarray(ref.convert("RGB"))
        ref_gray = cv2.cvtColor(ref_rgb, cv2.COLOR_RGB2GRAY)
        k2, d2 = cv2.SIFT_create().detectAndCompute(ref_gray, None)
        stat = {"kp_recv": 0 if k1 is None else len(k1),
                "kp_ref": 0 if k2 is None else len(k2),
                "good": 0, "inliers": 0}
        if d1 is None or d2 is None or len(k1) < self.min_matches or len(k2) < self.min_matches:
            return None, stat

        raw = cv2.BFMatcher(cv2.NORM_L2).knnMatch(d1, d2, k=2)
        good = [m for m, n in raw if m.distance < self.ratio * n.distance]
        stat["good"] = len(good)
        if len(good) < self.min_matches:
            return None, stat

        src = np.float32([k1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([k2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        H, mask = cv2.findHomography(src, dst, cv2.RANSAC, self.ransac_thresh)
        if H is None:
            return None, stat
        stat["inliers"] = int(mask.sum()) if mask is not None else 0

        rw, rh = ref.size
        warped = cv2.warpPerspective(recv_rgb, H, (rw, rh))
        return Image.fromarray(warped), stat

    def warp_to_reference(self, recv: Image.Image, ref: Image.Image
                          ) -> Tuple[Optional[Image.Image], dict]:
        recv_rgb, k1, d1 = self.features(recv)
        return self.warp_with_features(recv_rgb, k1, d1, ref)

    # ------------------------------------------------------------------ blind
    def blind_candidates(self, recv: Image.Image, *, min_area_frac: float = 0.03,
                         border_px: int = 6, uniform_std_max: float = 26.0
                         ) -> Tuple[list, dict]:
        """Reference-free geometric normalization for solid-background composites.

        When a watermarked image is dropped onto a roughly uniform canvas
        (optionally rotated / letterboxed), segment the foreground by *background
        colour distance*, take the largest foreground component, deskew it with
        ``minAreaRect`` and return upright crops in all 4 orientations (the true
        one is resolved by whoever gets a registry hit).

        Returns ``([], stat)`` when the background is not uniform enough to
        segment reliably (e.g. the image sits on another photo) or the foreground
        rectangle is implausible — those cases need a reference (SIFT).
        """
        if cv2 is None:
            raise DependencyError(key="error.dependency_cv2")

        rgb = np.asarray(recv.convert("RGB")).astype(np.float32)
        h, w = rgb.shape[:2]

        border = np.concatenate([
            rgb[:border_px].reshape(-1, 3), rgb[-border_px:].reshape(-1, 3),
            rgb[:, :border_px].reshape(-1, 3), rgb[:, -border_px:].reshape(-1, 3),
        ])
        bg = np.median(border, axis=0)
        border_std = float(border.std(axis=0).mean())
        stat = {"bg": [round(float(x), 1) for x in bg],
                "border_std": round(border_std, 1), "angle": None, "patch": None}
        if border_std > uniform_std_max:
            stat["skipped"] = "non-uniform background"
            return [], stat

        dist = np.sqrt(((rgb - bg) ** 2).sum(axis=2))
        thresh = max(30.0, 4.0 * border_std)
        mask = (dist > thresh).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        stat["contours"] = len(contours)
        if not contours:
            return [], stat

        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        stat["area_frac"] = round(float(area) / (w * h), 4)
        if area < min_area_frac * w * h:
            return [], stat

        rect = cv2.minAreaRect(largest)
        (cx, cy), (rw, rh), angle = rect
        rw, rh = int(round(rw)), int(round(rh))
        if rw < 16 or rh < 16:
            return [], stat
        # Reject when the component barely fills its bounding rectangle (i.e. it is
        # an irregular/occluded blob, not a clean rectangle) -> needs a reference.
        stat["rect_fill"] = round(float(area) / max(1, rw * rh), 3)
        stat["angle"] = round(float(angle), 2)
        stat["patch"] = [rw, rh]
        if stat["rect_fill"] < 0.80:
            stat["skipped"] = "foreground not rectangular (occluded?)"
            return [], stat

        rgb_u8 = np.asarray(recv.convert("RGB"))
        M = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
        rotated = cv2.warpAffine(rgb_u8, M, (w, h), flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REPLICATE)
        patch = cv2.getRectSubPix(rotated, (rw, rh), (cx, cy))

        base = Image.fromarray(patch)
        candidates = [
            base,
            base.transpose(Image.ROTATE_90),
            base.transpose(Image.ROTATE_180),
            base.transpose(Image.ROTATE_270),
        ]
        return candidates, stat


__all__ = ["GeometricSynchronizer"]
