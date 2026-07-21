"""Key derivation shared by all layers."""

from __future__ import annotations

import hashlib
import os

DEFAULT_SEED = 1337
_ARGON2_TIME_COST = 3
_ARGON2_MEMORY_COST = 65536
_ARGON2_PARALLELISM = 4
_ARGON2_HASH_LEN = 32


def _argon2id_key(password: str, *, salt: bytes, length: int = _ARGON2_HASH_LEN) -> bytes:
    from argon2 import low_level

    return low_level.hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=_ARGON2_TIME_COST,
        memory_cost=_ARGON2_MEMORY_COST,
        parallelism=_ARGON2_PARALLELISM,
        hash_len=length,
        type=low_level.Type.ID,
    )


def derive_key_bytes(key, *, context: str = "stashpix", length: int = 32) -> bytes:
    """Derive a symmetric key from a password or integer seed."""
    if key is None:
        key = DEFAULT_SEED
    if isinstance(key, int):
        digest = hashlib.sha256(f"{context}:{key}".encode()).digest()
        return digest[:length]
    salt = hashlib.sha256(f"{context}:salt:v1".encode()).digest()[:16]
    return _argon2id_key(str(key), salt=salt, length=length)


def derive_seed(key, default: int = DEFAULT_SEED) -> int:
    """Deterministically turn a key/password into an integer seed (permutation RNG)."""
    if key is None:
        return default
    if isinstance(key, int):
        return key
    material = derive_key_bytes(key, context="stashpix-seed", length=8)
    return int.from_bytes(material, "big")


def registry_master_key() -> bytes:
    """Load or create the local registry encryption key."""
    from ..paths import registry_key_path

    env = os.environ.get("STASHPIX_REGISTRY_KEY")
    if env:
        return hashlib.sha256(env.encode("utf-8")).digest()

    path = registry_key_path()
    if path.is_file():
        raw = path.read_bytes()
        if len(raw) >= 32:
            return raw[:32]

    material = os.urandom(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(material)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return material


__all__ = ["derive_seed", "derive_key_bytes", "registry_master_key", "DEFAULT_SEED"]
