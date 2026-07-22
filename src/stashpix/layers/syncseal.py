"""Optional SyncSeal geometric synchronization (TorchScript, CPU-friendly).

Embeds an imperceptible sync watermark; on extract predicts corner points and
unwarps the image before the primary robust DCT layer is read.

Requires torch + torchvision and a downloaded ``syncmodel.jit.pt`` checkpoint
(see ``core.model_store``). Off by default.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from PIL import Image

from ..core.base import EmbedOutcome, LayerResult
from ..core.model_store import resolve_syncseal_path

_log = logging.getLogger(__name__)

_model = None
_device = None
_load_error: Optional[str] = None


def torch_available() -> bool:
    try:
        import torch  # noqa: F401
        import torchvision  # noqa: F401
        return True
    except ImportError:
        return False


def _get_device():
    import torch
    return torch.device("cpu")


def _pil_to_batch(img: Image.Image):
    import torch
    from torchvision.transforms.functional import to_tensor
    return to_tensor(img.convert("RGB")).unsqueeze(0)


def _batch_to_pil(batch) -> Image.Image:
    import torch
    from torchvision.transforms.functional import to_pil_image
    t = batch[0].detach().clamp(0, 1).cpu()
    return to_pil_image(t)


def load_model(*, download: bool = True):
    """Load (and cache) the SyncSeal TorchScript model on CPU."""
    global _model, _device, _load_error
    if _model is not None:
        return _model
    if _load_error is not None:
        return None
    if not torch_available():
        _load_error = "torch/torchvision not installed"
        return None
    import torch
    path = resolve_syncseal_path(download=download)
    if path is None:
        _load_error = "SyncSeal checkpoint missing"
        return None
    try:
        _device = _get_device()
        _model = torch.jit.load(str(path), map_location=_device).to(_device).eval()
        return _model
    except Exception as exc:
        _load_error = str(exc)
        _log.warning("SyncSeal load failed: %s", exc)
        return None


def unload_model() -> None:
    global _model, _device, _load_error
    _model = None
    _device = None
    # keep _load_error so we do not retry endlessly in one process? clear it:
    _load_error = None


class SyncSealLayer:
    """Optional sync watermark layer (not a full Layer ABC — engine-specific)."""

    name_key = "layer.syncseal.name"

    def available(self, *, download: bool = False) -> bool:
        return load_model(download=download) is not None

    def last_error(self) -> Optional[str]:
        return _load_error

    def embed(self, image: Image.Image, message: str, config) -> EmbedOutcome:
        del message  # sync payload is learned; primary message is elsewhere
        model = load_model(download=True)
        if model is None:
            return EmbedOutcome(image=image, info={"skipped": True, "reason": _load_error})
        import torch
        img_pt = _pil_to_batch(image).to(_device)
        with torch.no_grad():
            emb = model.embed(img_pt)
        out = _batch_to_pil(emb["imgs_w"])
        if out.size != image.size:
            out = out.resize(image.size, Image.LANCZOS)
        return EmbedOutcome(image=out, info={"shell": "syncseal", "device": str(_device)})

    def unwarp(self, image: Image.Image, config) -> Tuple[Optional[Image.Image], Dict[str, Any]]:
        """Detect geometric warp and return rectified image, or (None, info)."""
        del config
        model = load_model(download=True)
        if model is None:
            return None, {"skipped": True, "reason": _load_error}
        import torch
        img_pt = _pil_to_batch(image).to(_device)
        h, w = img_pt.shape[-2:]
        with torch.no_grad():
            det = model.detect(img_pt)
            pred_pts = det["preds_pts"]
            unwarped = model.unwarp(img_pt, pred_pts, original_size=(h, w))
        out = _batch_to_pil(unwarped)
        if out.size != image.size:
            out = out.resize(image.size, Image.LANCZOS)
        info = {
            "used": True,
            "device": str(_device),
            "preds_pts_shape": list(pred_pts.shape),
        }
        return out, info

    def extract(self, image: Image.Image, config) -> Optional[LayerResult]:
        """SyncSeal does not carry the registry message — only unwarps."""
        unwarped, info = self.unwarp(image, config)
        if unwarped is None:
            return None
        return LayerResult(message=None, layer_key=self.name_key, info={**info, "image": unwarped})


__all__ = ["SyncSealLayer", "load_model", "unload_model", "torch_available"]
