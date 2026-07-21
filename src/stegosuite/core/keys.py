"""Key derivation shared by all layers."""

from __future__ import annotations

import hashlib

DEFAULT_SEED = 1337


def derive_seed(key, default: int = DEFAULT_SEED) -> int:
    """Deterministically turn a key/password into an integer seed.

    ``None`` -> ``default``; an int passes through; a string is hashed (SHA-256).
    """
    if key is None:
        return default
    if isinstance(key, int):
        return key
    digest = hashlib.sha256(str(key).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


__all__ = ["derive_seed", "DEFAULT_SEED"]
