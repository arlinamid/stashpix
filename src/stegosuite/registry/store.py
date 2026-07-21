"""JSON-backed registry mapping robust-watermark IDs to the full messages.

The robust watermark only carries a 128-bit ID; the actual message lives here and
is looked up by ID. The class is intentionally small and swappable — a database
backend could implement the same interface for a real SaaS deployment.
"""

from __future__ import annotations

import os
import json
import datetime
from typing import Any, Dict, Optional

from ..paths import default_registry_path, REFS_DIRNAME


class Registry:
    """A simple JSON key-value store of ID -> entry."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or default_registry_path()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save(self, data: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add(self, id_hex: str, message: str, *, source_image: str = "",
            output_image: str = "", meta: Optional[Dict[str, Any]] = None) -> None:
        data = self._load()
        data[id_hex] = {
            "message": message,
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "source_image": source_image,
            "output_image": output_image,
            "meta": meta or {},
        }
        self._save(data)

    def refs_dir(self) -> str:
        """Directory holding managed reference images (for auto geo-matching)."""
        return os.path.join(os.path.dirname(os.path.abspath(self.path)), REFS_DIRNAME)

    def save_reference(self, id_hex: str, image, *, max_width: int = 800) -> Optional[str]:
        """Store a downscaled copy of the stego image for later SIFT retrieval.

        Returns the saved path, or ``None`` if the id is unknown.
        """
        data = self._load()
        if id_hex not in data:
            return None
        img = image.convert("RGB")
        w, h = img.size
        if w > max_width:
            img = img.resize((max_width, max(1, round(max_width * h / w))))
        os.makedirs(self.refs_dir(), exist_ok=True)
        path = os.path.join(self.refs_dir(), f"{id_hex}.png")
        img.save(path)
        data[id_hex]["reference"] = os.path.basename(path)
        self._save(data)
        return path

    def reference_path(self, id_hex: str) -> Optional[str]:
        """Resolve a usable geometry reference image path for ``id_hex``.

        Only the *frame/geometry* of the reference is used (SIFT), not its pixels,
        so any image with the embed-time content and resolution works. Preference:
        the managed copy saved at embed time, then the original source image, then
        the output image — each resolved next to the registry or in the cwd.
        """
        entry = self._load().get(id_hex)
        if not entry:
            return None
        managed = os.path.join(self.refs_dir(), f"{id_hex}.png")
        if os.path.exists(managed):
            return managed
        for field in ("source_image", "output_image"):
            name = entry.get(field)
            if not name:
                continue
            for base in (os.path.dirname(os.path.abspath(self.path)), os.getcwd()):
                cand = name if os.path.isabs(name) else os.path.join(base, name)
                if os.path.exists(cand):
                    return cand
        return None

    def get(self, id_hex: str) -> Optional[Dict[str, Any]]:
        return self._load().get(id_hex)

    def message_for(self, id_hex: str) -> Optional[str]:
        entry = self.get(id_hex)
        return entry["message"] if entry else None

    def all(self) -> Dict[str, Any]:
        return self._load()

    def remove(self, id_hex: str) -> bool:
        data = self._load()
        if id_hex in data:
            del data[id_hex]
            self._save(data)
            return True
        return False


__all__ = ["Registry", "default_registry_path"]
