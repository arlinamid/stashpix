"""Key derivation shared by all layers.

There are two distinct classes of secret here, and conflating them is what the
pre-1.5.0 code got wrong.

**Portable secrets** are reconstructed from the user's password alone, because
that is all a decoder ever has: someone hands you a stego image and a password.
Anything machine-bound here would make an image embedded on one computer
unreadable on another, which defeats the product. Two things fall in this class:

* the *permutation seed* (which DCT blocks / LSB positions carry which bit).
  This cannot take a random salt -- the salt would have to be read from the
  image, but you need the permutation to read anything from the image at all.
  It is therefore Argon2id over the password with a fixed protocol constant.
  That constant is a domain separator, not a secret, and it is deliberately not
  what protects confidentiality.
* the *content key* (AES-GCM over the payload). This one *can* be salted,
  because the salt travels in the payload as plaintext, and salts are public by
  design. Every embed draws a fresh 16-byte salt, so the same password never
  produces the same key twice and precomputation buys an attacker nothing. This
  is where confidentiality actually lives.

**Local secrets** never leave the machine, so they are bound to it. The registry
encryption key mixes stored random material with a user+machine fingerprint, so
lifting the key file alone onto another box does not decrypt the registry.

Before 1.5.0 ``derive_key_bytes`` used one hardcoded salt
(``sha256("stashpix:salt:v1")``) for everything, which made every password map
to one globally fixed key -- rainbow-table territory -- and ``DEFAULT_SEED``
silently backed unkeyed embeds with the constant 1337, so anyone could read
them.
"""

from __future__ import annotations

import getpass
import hashlib
import os
import platform
import uuid
from typing import Union

from ..exceptions import StegoError

_ARGON2_TIME_COST = 3
_ARGON2_MEMORY_COST = 65536
_ARGON2_PARALLELISM = 4
_ARGON2_HASH_LEN = 32

CONTENT_SALT_BYTES = 16

# Domain separator for the unsaltable permutation seed. Public protocol
# constant, not a secret: it only keeps the seed from colliding with keys
# derived for other purposes from the same password.
_SEED_DOMAIN = b"stashpix/seed/v3"

KeyLike = Union[str, int]


def require_key(key) -> KeyLike:
    """Every entry point goes through here. There is no default key.

    Returning a constant for a missing password (the old ``DEFAULT_SEED = 1337``)
    means anyone can read the result, while the output still looks encrypted.
    Failing loudly is the only honest option.
    """
    if key is None:
        raise StegoError(key="error.key_required")
    if isinstance(key, int):
        return key
    text = str(key)
    if not text.strip():
        raise StegoError(key="error.key_required")
    return text


def _argon2id(password: bytes, *, salt: bytes, length: int) -> bytes:
    from argon2 import low_level

    return low_level.hash_secret_raw(
        secret=password,
        salt=salt,
        time_cost=_ARGON2_TIME_COST,
        memory_cost=_ARGON2_MEMORY_COST,
        parallelism=_ARGON2_PARALLELISM,
        hash_len=length,
        type=low_level.Type.ID,
    )


def new_content_salt() -> bytes:
    """Fresh per-message salt for the content key. Stored in the payload."""
    return os.urandom(CONTENT_SALT_BYTES)


def derive_content_key(key, salt: bytes, *, context: str = "stashpix-lsb-v3",
                       length: int = _ARGON2_HASH_LEN) -> bytes:
    """Derive the AEAD content key from the password and a per-message salt.

    ``salt`` must come from ``new_content_salt()`` at embed time and be read back
    out of the payload at extract time. Passing a fixed value here reintroduces
    the pre-1.5.0 weakness.
    """
    key = require_key(key)
    if len(salt) < CONTENT_SALT_BYTES:
        raise ValueError(f"content salt must be >= {CONTENT_SALT_BYTES} bytes")
    if isinstance(key, int):
        material = f"{context}:{key}".encode()
        return hashlib.pbkdf2_hmac("sha256", material, salt, 200_000, length)
    return _argon2id(f"{context}:{key}".encode("utf-8"), salt=salt, length=length)


def derive_seed(key) -> int:
    """Password -> integer seed for the bit-placement permutation.

    Unsaltable by construction: the decoder needs this before it can read a
    single bit, so there is nowhere to put a salt it could recover. Argon2id
    keeps brute-forcing expensive; confidentiality rests on the salted content
    key, not on this.
    """
    key = require_key(key)
    if isinstance(key, int):
        return key
    material = _argon2id(str(key).encode("utf-8"), salt=_SEED_DOMAIN[:16], length=8)
    return int.from_bytes(material, "big")


# ---------------------------------------------------------------- local only

def machine_fingerprint() -> bytes:
    """Stable user+machine identity for binding local at-rest secrets.

    Only ever mixed into secrets that stay on this machine. Never feeds anything
    that has to be reproducible elsewhere -- see the module docstring.
    """
    parts = [
        platform.node(),
        platform.machine(),
        platform.system(),
        str(uuid.getnode()),          # MAC-derived host id
    ]
    try:
        parts.append(getpass.getuser())
    except Exception:
        parts.append(os.environ.get("USERNAME") or os.environ.get("USER") or "?")
    return hashlib.sha256("\x1f".join(parts).encode("utf-8", "replace")).digest()


def _install_material() -> bytes:
    """Load or create this installation's random root secret (0600)."""
    from ..paths import registry_key_path

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


def registry_master_key(*, bind_machine: bool = True) -> bytes:
    """Key for the local encrypted registry.

    Mixes the stored random material with ``machine_fingerprint()`` so copying
    the key file to another machine is not enough to decrypt a copied registry.
    ``bind_machine=False`` reproduces the pre-1.5.0 derivation and exists only so
    an existing registry can still be read and re-encrypted.
    """
    env = os.environ.get("STASHPIX_REGISTRY_KEY")
    if env:
        return hashlib.sha256(env.encode("utf-8")).digest()

    material = _install_material()
    if not bind_machine:
        return material
    return hashlib.blake2b(material + machine_fingerprint(),
                           digest_size=32, person=b"stashpix-reg-v2").digest()


__all__ = [
    "CONTENT_SALT_BYTES",
    "KeyLike",
    "require_key",
    "new_content_salt",
    "derive_content_key",
    "derive_seed",
    "machine_fingerprint",
    "registry_master_key",
]
