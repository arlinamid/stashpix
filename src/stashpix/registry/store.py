"""Encrypted JSON-backed registry mapping robust-watermark IDs to messages."""

from __future__ import annotations

import datetime
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from ..core.crypto import aead_decrypt, aead_encrypt, b64_decode, b64_encode
from ..core.keys import registry_master_key
from ..core.perceptual import dhash_hex, edge_hash_hex, hamming_hex, phash_hex
from ..paths import REFS_DIRNAME, default_registry_path

# v2 binds the encryption key to this user+machine, so lifting the key file
# alone onto another box does not decrypt a copied registry. v1 (unbound) is
# still read so an existing registry survives the upgrade -- it is re-encrypted
# as v2 on the next write.
REGISTRY_FORMAT = "stashpix-registry-v2"
LEGACY_REGISTRY_FORMAT = "stashpix-registry-v1"
PHASH_TOP_K = 10


class Registry:
    """Encrypted key-value store of ID -> entry."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or default_registry_path()

    def _load_plain(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {}
        with open(self.path, "r", encoding="utf-8") as f:
            wrapper = json.load(f)
        if not isinstance(wrapper, dict):
            return {}
        fmt = wrapper.get("format")
        if fmt not in (REGISTRY_FORMAT, LEGACY_REGISTRY_FORMAT):
            # Legacy plaintext JSON (pre-1.3.0) — read directly and re-save encrypted.
            if wrapper and all(isinstance(v, dict) for v in wrapper.values()):
                return wrapper
            return {}
        nonce = b64_decode(wrapper["nonce"])
        ciphertext = b64_decode(wrapper["ciphertext"])
        key = registry_master_key(bind_machine=fmt == REGISTRY_FORMAT)
        raw = aead_decrypt(key, nonce, ciphertext, associated_data=fmt.encode())
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}

    def _save_plain(self, data: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        key = registry_master_key()
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        nonce, ciphertext = aead_encrypt(key, raw, associated_data=REGISTRY_FORMAT.encode())
        wrapper = {
            "format": REGISTRY_FORMAT,
            "nonce": b64_encode(nonce),
            "ciphertext": b64_encode(ciphertext),
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(wrapper, f, ensure_ascii=False, indent=2)

    def add(self, id_hex: str, message: str, *, source_image: str = "",
            output_image: str = "", meta: Optional[Dict[str, Any]] = None) -> None:
        data = self._load_plain()
        data[id_hex] = {
            "message": message,
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "source_image": source_image,
            "output_image": output_image,
            "meta": meta or {},
        }
        self._save_plain(data)

    def set_signature(self, id_hex: str, record: Dict[str, Any]) -> bool:
        """Attach an authorship signature record to an existing entry."""
        data = self._load_plain()
        if id_hex not in data:
            return False
        data[id_hex]["signature"] = record
        self._save_plain(data)
        return True

    def signature_for(self, id_hex: str) -> Optional[Dict[str, Any]]:
        entry = self.get(id_hex)
        return entry.get("signature") if entry else None

    def refs_dir(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(self.path)), REFS_DIRNAME)

    def save_reference(self, id_hex: str, image, *, max_width: int = 800) -> Optional[str]:
        data = self._load_plain()
        if id_hex not in data:
            return None
        img = image.convert("RGB")
        w, h = img.size
        if w > max_width:
            img = img.resize((max_width, max(1, round(max_width * h / w))))
        os.makedirs(self.refs_dir(), exist_ok=True)
        path = os.path.join(self.refs_dir(), f"{id_hex}.png")
        img.save(path)
        meta = data[id_hex].setdefault("meta", {})
        meta["phash"] = phash_hex(img)
        meta["dhash"] = dhash_hex(img)
        meta["edge_hash"] = edge_hash_hex(img)
        data[id_hex]["reference"] = os.path.basename(path)
        self._save_plain(data)
        return path

    def reference_path(self, id_hex: str) -> Optional[str]:
        entry = self._load_plain().get(id_hex)
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

    # NOTE: perceptual hashes only SHORTLIST candidates for the SIFT/robust path.
    # They must never attribute a message on their own — an unwatermarked copy of
    # the original cover has distance ~0 from the stored reference (the watermark
    # is invisible), so a hash match is not evidence that the image carries one.
    def _fingerprint_distance(self, query_image, meta: Dict[str, Any]) -> int:
        query_p = phash_hex(query_image)
        query_d = dhash_hex(query_image)
        query_e = edge_hash_hex(query_image)
        ref_p = meta.get("phash")
        ref_d = meta.get("dhash")
        ref_e = meta.get("edge_hash")
        if not (ref_p and ref_d):
            return 9999
        dist = hamming_hex(query_p, ref_p) + hamming_hex(query_d, ref_d)
        if ref_e:
            dist += hamming_hex(query_e, ref_e)
        return dist

    def ranked_reference_ids(self, query_image, *, top_k: int = PHASH_TOP_K) -> List[Tuple[str, int]]:
        """Shortlist registry IDs by perceptual-hash distance (lowest first).

        Ordering hint only — every candidate must still be confirmed by reading
        the actual watermark. See the note above ``_fingerprint_distance``.
        """
        scored: List[Tuple[str, int]] = []
        for id_hex, entry in self._load_plain().items():
            if not self.reference_path(id_hex):
                continue
            meta = entry.get("meta") or {}
            scored.append((id_hex, self._fingerprint_distance(query_image, meta)))
        scored.sort(key=lambda x: x[1])
        return scored[:top_k] if top_k > 0 else scored

    def get(self, id_hex: str) -> Optional[Dict[str, Any]]:
        return self._load_plain().get(id_hex)

    def message_for(self, id_hex: str) -> Optional[str]:
        entry = self.get(id_hex)
        return entry["message"] if entry else None

    def all(self) -> Dict[str, Any]:
        return self._load_plain()

    def remove(self, id_hex: str) -> bool:
        data = self._load_plain()
        if id_hex in data:
            del data[id_hex]
            self._save_plain(data)
            return True
        return False


__all__ = ["Registry", "default_registry_path", "PHASH_TOP_K"]
