"""AEAD helpers (AES-GCM) for payload and registry encryption."""

from __future__ import annotations

import base64
import os
from typing import Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_LEN = 12
_TAG_OVERHEAD = 16


def aead_encrypt(key: bytes, plaintext: bytes, *, associated_data: bytes = b"") -> Tuple[bytes, bytes]:
    """Return ``(nonce, ciphertext_with_tag)``."""
    if len(key) != 32:
        raise ValueError("AES-GCM key must be 32 bytes")
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext, associated_data)
    return nonce, ct


def aead_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, *, associated_data: bytes = b"") -> bytes:
    if len(key) != 32:
        raise ValueError("AES-GCM key must be 32 bytes")
    return AESGCM(key).decrypt(nonce, ciphertext, associated_data)


def pack_encrypted(nonce: bytes, ciphertext: bytes) -> bytes:
    return nonce + ciphertext


def unpack_encrypted(blob: bytes) -> Tuple[bytes, bytes]:
    if len(blob) < _NONCE_LEN + _TAG_OVERHEAD:
        raise ValueError("encrypted blob too short")
    return blob[:_NONCE_LEN], blob[_NONCE_LEN:]


def b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def b64_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text.encode("ascii"))


__all__ = [
    "aead_encrypt",
    "aead_decrypt",
    "pack_encrypted",
    "unpack_encrypted",
    "b64_encode",
    "b64_decode",
    "_NONCE_LEN",
]
