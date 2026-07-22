"""Optional WAM localization layer (Watermark Anything Model).

Embeds a 32-bit fingerprint (derived from the robust ID) and on extract returns
a ROI crop plus the decoded bits for registry shortlisting. Does not replace
the 128-bit DCT ID.

Requires torch + the MIT ``watermark-anything`` code (lazy-cloned) and
``wam_mit.pth``. Off by default.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from ..core.base import EmbedOutcome, LayerResult
from ..core.model_store import (
    add_wam_to_syspath,
    ensure_wam_repo,
    resolve_wam_checkpoint,
    resolve_wam_params,
)

_log = logging.getLogger(__name__)

_model = None
_device = None
_load_error: Optional[str] = None
NBITS = 32


def torch_available() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def id_hex_to_bits(id_hex: str, nbits: int = NBITS) -> List[int]:
    """Deterministic 32-bit fingerprint from a robust UUID hex."""
    digest = hashlib.sha256(id_hex.encode("ascii")).digest()
    bits: List[int] = []
    for byte in digest:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
            if len(bits) >= nbits:
                return bits[:nbits]
    return bits[:nbits]


def bits_to_hex(bits) -> str:
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    width = max(1, (len(bits) + 3) // 4)
    return f"{v:0{width}x}"


def _get_device():
    import torch
    return torch.device("cpu")


def _load_wam_from_checkpoint(json_path: str, ckpt_path: str, repo):
    """Minimal loader (avoids notebooks/matplotlib deps)."""
    import argparse
    import json
    import os

    import omegaconf
    import torch
    from watermark_anything.models import Wam, build_embedder, build_extractor
    from watermark_anything.augmentation.augmenter import Augmenter
    from watermark_anything.data.transforms import normalize_img, unnormalize_img
    from watermark_anything.modules.jnd import JND

    with open(json_path, "r", encoding="utf-8") as f:
        params = json.load(f)
    args = argparse.Namespace(**params)
    prev = os.getcwd()
    try:
        os.chdir(repo)
        embedder_cfg = omegaconf.OmegaConf.load(args.embedder_config)
        embedder_params = embedder_cfg[args.embedder_model]
        extractor_cfg = omegaconf.OmegaConf.load(args.extractor_config)
        extractor_params = extractor_cfg[args.extractor_model]
        augmenter_cfg = omegaconf.OmegaConf.load(args.augmentation_config)
        attenuation_cfg = omegaconf.OmegaConf.load(args.attenuation_config)
        embedder = build_embedder(args.embedder_model, embedder_params, args.nbits)
        extractor = build_extractor(extractor_cfg.model, extractor_params, args.img_size, args.nbits)
        augmenter = Augmenter(**augmenter_cfg)
        try:
            attenuation = JND(
                **attenuation_cfg[args.attenuation],
                preprocess=unnormalize_img,
                postprocess=normalize_img,
            )
        except Exception:
            attenuation = None
        wam = Wam(embedder, extractor, augmenter, attenuation, args.scaling_w, args.scaling_i)
        checkpoint = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        wam.load_state_dict(checkpoint)
        return wam
    finally:
        os.chdir(prev)


def load_model(*, download: bool = True):
    global _model, _device, _load_error
    if _model is not None:
        return _model
    if _load_error is not None:
        return None
    if not torch_available():
        _load_error = "torch not installed"
        return None
    ckpt = resolve_wam_checkpoint(download=download)
    params = resolve_wam_params(download=download)
    repo = ensure_wam_repo(download=download)
    if ckpt is None or params is None or repo is None:
        _load_error = "WAM checkpoint/params/repo missing"
        return None
    add_wam_to_syspath(repo)
    try:
        wam = _load_wam_from_checkpoint(str(params), str(ckpt), repo)
        _device = _get_device()
        _model = wam.to(_device).eval()
        return _model
    except Exception as exc:
        _load_error = str(exc)
        _log.warning("WAM load failed: %s", exc)
        return None


def unload_model() -> None:
    global _model, _device, _load_error
    _model = None
    _device = None
    _load_error = None


def _default_transform(img: Image.Image):
    from torchvision import transforms
    return transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225]),
    ])(img.convert("RGB"))


def _unnormalize_to_pil(t) -> Image.Image:
    import torch
    mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
    x = (t.detach().cpu() * std + mean).clamp(0, 1)
    arr = (x.permute(1, 2, 0).numpy() * 255.0).round().astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def _msg_predict(bit_preds, mask_preds):
    """Majority-vote bits under the predicted mask (WAM-style)."""
    import torch
    mask = (mask_preds > 0.5).float()  # [B,H,W]
    bits = (bit_preds > 0).float()     # [B,K,H,W]
    B, K, H, W = bits.shape
    out = []
    for b in range(B):
        m = mask[b].view(1, H * W)
        flat = bits[b].view(K, H * W)
        if m.sum() < 1:
            out.append(torch.zeros(K))
            continue
        scored = (flat * m).sum(dim=1) / m.sum().clamp(min=1)
        out.append((scored > 0.5).float())
    return torch.stack(out, dim=0)


class WamLocalLayer:
    name_key = "layer.wam.name"

    def available(self, *, download: bool = False) -> bool:
        return load_model(download=download) is not None

    def last_error(self) -> Optional[str]:
        return _load_error

    def embed(self, image: Image.Image, message: str, config, *,
              id_hex: Optional[str] = None) -> EmbedOutcome:
        del message
        model = load_model(download=True)
        if model is None or not id_hex:
            return EmbedOutcome(
                image=image,
                info={"skipped": True, "reason": _load_error or "no id_hex"},
            )
        import torch
        bits = id_hex_to_bits(id_hex)
        wm_msg = torch.tensor(bits, dtype=torch.float32, device=_device).unsqueeze(0)
        img_pt = _default_transform(image).unsqueeze(0).to(_device)
        with torch.no_grad():
            outputs = model.embed(img_pt, wm_msg)
            imgs_w = outputs["imgs_w"]
        out = _unnormalize_to_pil(imgs_w[0])
        if out.size != image.size:
            out = out.resize(image.size, Image.LANCZOS)
        return EmbedOutcome(
            image=out,
            info={
                "shell": "wam",
                "nbits": NBITS,
                "fingerprint": bits_to_hex(bits),
                "id_hex": id_hex,
                "device": str(_device),
            },
        )

    def localize(self, image: Image.Image, config
                 ) -> Tuple[Optional[Image.Image], Dict[str, Any]]:
        """Return ROI crop (or full image) and detection info including bits."""
        del config
        model = load_model(download=True)
        if model is None:
            return None, {"skipped": True, "reason": _load_error}
        import torch
        import torch.nn.functional as F
        ow, oh = image.size
        img_pt = _default_transform(image).unsqueeze(0).to(_device)
        with torch.no_grad():
            preds = model.detect(img_pt)["preds"]  # [1, 33, 256, 256]
            mask_preds = torch.sigmoid(preds[:, 0, :, :])
            bit_preds = preds[:, 1:, :, :]
            pred_message = _msg_predict(bit_preds, mask_preds)[0]
        bits = [int(x) for x in pred_message.cpu().tolist()]
        mask_np = mask_preds[0].detach().cpu().numpy()
        ys, xs = np.where(mask_np > 0.5)
        info: Dict[str, Any] = {
            "used": True,
            "fingerprint": bits_to_hex(bits),
            "bits": bits,
            "mask_coverage": float(mask_np.mean()),
            "device": str(_device),
        }
        if len(xs) < 8 or len(ys) < 8:
            info["roi"] = "full"
            return image.convert("RGB"), info
        # Map 256-grid coords to original pixels
        y0 = int(ys.min() * oh / mask_np.shape[0])
        y1 = int((ys.max() + 1) * oh / mask_np.shape[0])
        x0 = int(xs.min() * ow / mask_np.shape[1])
        x1 = int((xs.max() + 1) * ow / mask_np.shape[1])
        pad_x = max(8, (x1 - x0) // 10)
        pad_y = max(8, (y1 - y0) // 10)
        x0, y0 = max(0, x0 - pad_x), max(0, y0 - pad_y)
        x1, y1 = min(ow, x1 + pad_x), min(oh, y1 + pad_y)
        if (x1 - x0) < 32 or (y1 - y0) < 32:
            info["roi"] = "full"
            return image.convert("RGB"), info
        crop = image.convert("RGB").crop((x0, y0, x1, y1))
        info["roi"] = {"box": [x0, y0, x1, y1]}
        return crop, info

    def extract(self, image: Image.Image, config) -> Optional[LayerResult]:
        crop, info = self.localize(image, config)
        if crop is None:
            return None
        info["image"] = crop
        return LayerResult(message=None, layer_key=self.name_key, info=info)


__all__ = [
    "WamLocalLayer",
    "load_model",
    "unload_model",
    "torch_available",
    "id_hex_to_bits",
    "bits_to_hex",
    "NBITS",
]
