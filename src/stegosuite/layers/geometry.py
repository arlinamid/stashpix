"""Geometric synchronizer — SIFT re-alignment (homography + TPS).

If a watermarked image was placed into another image (translated/scaled/rotated)
and/or partially occluded, this warps the received image back onto the reference
(the registered/encoded image) so the DCT watermark grid lines up again.

Two warp modes:
  * **homography** — global projective transform (perspective / rotate / scale).
  * **tps** — Thin-Plate Spline over SIFT matches, with local-MAD outlier
    filtering and optional dense DIS optical-flow refine, for *non-linear*
    morphs (swirl, elastic, wave). Classical idea: locally linear approximation
    of a global non-rigid warp, then dense residual alignment.

OpenCV is an optional dependency; :class:`GeometricSynchronizer.available`
reports whether it can be used.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

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
                 ransac_thresh: float = 5.0, tps_ctrl: int = 128,
                 tps_filter: bool = True, tps_flow: bool = True):
        self.min_matches = min_matches
        self.ratio = ratio
        self.ransac_thresh = ransac_thresh
        self.tps_ctrl = tps_ctrl          # max TPS control points
        self.tps_filter = tps_filter      # local-MAD outlier rejection
        self.tps_flow = tps_flow          # dense optical-flow refine after TPS

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

    def _match(self, k1, d1, ref: Image.Image) -> Tuple[Optional[np.ndarray],
                                                         Optional[np.ndarray], dict]:
        """Return (src_pts Nx2 in recv, dst_pts Nx2 in ref, stat) or (None, None, stat)."""
        if cv2 is None:
            raise DependencyError(key="error.dependency_cv2")
        ref_rgb = np.asarray(ref.convert("RGB"))
        ref_gray = cv2.cvtColor(ref_rgb, cv2.COLOR_RGB2GRAY)
        k2, d2 = cv2.SIFT_create().detectAndCompute(ref_gray, None)
        stat = {"kp_recv": 0 if k1 is None else len(k1),
                "kp_ref": 0 if k2 is None else len(k2),
                "good": 0, "inliers": 0, "mode": None}
        if d1 is None or d2 is None or len(k1) < self.min_matches or len(k2) < self.min_matches:
            return None, None, stat

        raw = cv2.BFMatcher(cv2.NORM_L2).knnMatch(d1, d2, k=2)
        good = [m for m, n in raw if m.distance < self.ratio * n.distance]
        stat["good"] = len(good)
        if len(good) < self.min_matches:
            return None, None, stat

        src = np.float32([k1[m.queryIdx].pt for m in good])
        dst = np.float32([k2[m.trainIdx].pt for m in good])
        return src, dst, stat

    def warp_with_features(self, recv_rgb, k1, d1, ref: Image.Image
                           ) -> Tuple[Optional[Image.Image], dict]:
        """Warp via global homography (perspective / affine-ish geometry)."""
        src, dst, stat = self._match(k1, d1, ref)
        if src is None:
            return None, stat
        src_h = src.reshape(-1, 1, 2)
        dst_h = dst.reshape(-1, 1, 2)
        H, mask = cv2.findHomography(src_h, dst_h, cv2.RANSAC, self.ransac_thresh)
        if H is None:
            return None, stat
        stat["inliers"] = int(mask.sum()) if mask is not None else 0
        stat["mode"] = "homography"
        rw, rh = ref.size
        warped = cv2.warpPerspective(recv_rgb, H, (rw, rh))
        return Image.fromarray(warped), stat

    def warp_tps_with_features(self, recv_rgb, k1, d1, ref: Image.Image
                               ) -> Tuple[Optional[Image.Image], dict]:
        """Warp via Thin-Plate Spline (+ optional dense flow) for non-linear morphs.

        Pipeline:
          1. SIFT matches (recv → ref)
          2. optional local-MAD outlier filter
          3. spatially subsampled TPS control points
          4. TPS remap onto the reference canvas
          5. optional DIS optical-flow refine (helps periodic wave / strong elastic)
        """
        src, dst, stat = self._match(k1, d1, ref)
        if src is None:
            return None, stat
        n_raw = len(src)
        if self.tps_filter:
            src, dst = self._filter_outliers(src, dst)
        ctrl_src, ctrl_dst = self._subsample_ctrl(src, dst, self.tps_ctrl)
        if len(ctrl_src) < self.min_matches:
            return None, stat
        stat["inliers"] = len(ctrl_src)
        stat["matches_raw"] = n_raw
        stat["matches_filtered"] = len(src)
        stat["mode"] = "tps"
        rw, rh = ref.size
        try:
            warped = self._tps_remap(recv_rgb, ctrl_src, ctrl_dst, (rw, rh))
            if self.tps_flow:
                warped = self._flow_refine(warped, np.asarray(ref.convert("RGB")))
                stat["mode"] = "tps+flow"
        except Exception:  # noqa: BLE001 — fall through to caller
            return None, {**stat, "tps_error": True}
        return Image.fromarray(warped), stat

    def warp_to_reference(self, recv: Image.Image, ref: Image.Image
                          ) -> Tuple[Optional[Image.Image], dict]:
        recv_rgb, k1, d1 = self.features(recv)
        return self.warp_with_features(recv_rgb, k1, d1, ref)

    def warp_tps_to_reference(self, recv: Image.Image, ref: Image.Image
                              ) -> Tuple[Optional[Image.Image], dict]:
        recv_rgb, k1, d1 = self.features(recv)
        return self.warp_tps_with_features(recv_rgb, k1, d1, ref)

    # --------------------------------------------------------------- TPS math
    @staticmethod
    def _filter_outliers(src: np.ndarray, dst: np.ndarray, k: int = 8,
                         mad_k: float = 3.0) -> Tuple[np.ndarray, np.ndarray]:
        """Drop matches whose displacement disagrees with the local neighbourhood."""
        n = len(src)
        if n < k + 2:
            return src, dst
        disp = src - dst
        keep = np.ones(n, dtype=bool)
        for i in range(n):
            d2 = np.sum((dst - dst[i]) ** 2, axis=1)
            nn = np.argpartition(d2, min(k, n - 1))[: k + 1]
            nn = nn[nn != i][:k]
            if len(nn) == 0:
                continue
            med = np.median(disp[nn], axis=0)
            resid = float(np.linalg.norm(disp[i] - med))
            local = np.linalg.norm(disp[nn] - med, axis=1)
            scale = max(1.0, float(np.median(local)) * 1.4826)
            if resid > mad_k * scale:
                keep[i] = False
        if int(keep.sum()) < 15:
            return src, dst
        return src[keep], dst[keep]

    @staticmethod
    def _subsample_ctrl(src: np.ndarray, dst: np.ndarray, max_n: int
                        ) -> Tuple[np.ndarray, np.ndarray]:
        """Pick spatially spread control points (grid bins) for a stable TPS."""
        n = len(src)
        if n <= max_n:
            return src, dst
        xs, ys = dst[:, 0], dst[:, 1]
        bins = max(2, int(np.ceil(np.sqrt(max_n))))
        x_edges = np.linspace(xs.min() - 1e-3, xs.max() + 1e-3, bins + 1)
        y_edges = np.linspace(ys.min() - 1e-3, ys.max() + 1e-3, bins + 1)
        xi = np.clip(np.digitize(xs, x_edges) - 1, 0, bins - 1)
        yi = np.clip(np.digitize(ys, y_edges) - 1, 0, bins - 1)
        chosen: List[int] = []
        for bx in range(bins):
            for by in range(bins):
                idxs = np.where((xi == bx) & (yi == by))[0]
                if len(idxs) == 0:
                    continue
                cx = 0.5 * (x_edges[bx] + x_edges[bx + 1])
                cy = 0.5 * (y_edges[by] + y_edges[by + 1])
                d2 = (xs[idxs] - cx) ** 2 + (ys[idxs] - cy) ** 2
                chosen.append(int(idxs[int(np.argmin(d2))]))
        if len(chosen) < max_n // 2:
            step = max(1, n // max_n)
            chosen = list(range(0, n, step))[:max_n]
        else:
            chosen = chosen[:max_n]
        idx = np.array(chosen, dtype=np.int32)
        return src[idx], dst[idx]

    @staticmethod
    def _tps_remap(recv_rgb: np.ndarray, src: np.ndarray, dst: np.ndarray,
                   out_size: Tuple[int, int]) -> np.ndarray:
        """Sample ``recv`` onto a ``out_size`` (W,H) canvas via TPS: ref→recv.

        Control pairs: ``dst`` = points in the reference (output) canvas,
        ``src`` = corresponding points in the receive image (input).
        """
        if cv2 is None:
            raise DependencyError(key="error.dependency_cv2")
        tps = cv2.createThinPlateSplineShapeTransformer()
        shape_from = dst.reshape(1, -1, 2).astype(np.float32)
        shape_to = src.reshape(1, -1, 2).astype(np.float32)
        matches = [cv2.DMatch(i, i, 0) for i in range(len(src))]
        tps.estimateTransformation(shape_from, shape_to, matches)
        w, h = out_size
        grid = np.stack(np.meshgrid(np.arange(w, dtype=np.float32),
                                    np.arange(h, dtype=np.float32)), axis=-1)
        flat = grid.reshape(1, -1, 2)
        transformed = tps.applyTransformation(flat)[1]
        map_xy = transformed.reshape(h, w, 2)
        map_x = map_xy[:, :, 0].astype(np.float32)
        map_y = map_xy[:, :, 1].astype(np.float32)
        return cv2.remap(recv_rgb, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_REPLICATE)

    @staticmethod
    def _flow_refine(warped_rgb: np.ndarray, ref_rgb: np.ndarray) -> np.ndarray:
        """Dense DIS optical-flow refine: sample ``warped`` onto ``ref`` pixels."""
        if cv2 is None:
            raise DependencyError(key="error.dependency_cv2")
        g_w = cv2.cvtColor(warped_rgb, cv2.COLOR_RGB2GRAY)
        g_r = cv2.cvtColor(ref_rgb, cv2.COLOR_RGB2GRAY)
        if g_w.shape != g_r.shape:
            warped_rgb = cv2.resize(warped_rgb, (g_r.shape[1], g_r.shape[0]),
                                    interpolation=cv2.INTER_LINEAR)
            g_w = cv2.cvtColor(warped_rgb, cv2.COLOR_RGB2GRAY)
        dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        # flow at each ref pixel: where to sample in the (coarse) warped image
        flow = dis.calc(g_r, g_w, None)
        hh, ww = g_r.shape
        xx, yy = np.meshgrid(np.arange(ww), np.arange(hh))
        map_x = (xx + flow[..., 0]).astype(np.float32)
        map_y = (yy + flow[..., 1]).astype(np.float32)
        return cv2.remap(warped_rgb, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_REPLICATE)

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
