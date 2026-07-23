"""Ed25519 authorship signatures — the non-repudiable half of "I made this".

The robust watermark physically binds a 128-bit UUID to the pixels; it survives
JPEG/resize/crop. But a UUID in a registry proves only that *a* watermark is
present. It does not, on its own, prove *who* asserted ownership, or *when* —
anyone who can write the registry could mint a competing entry.

This module closes that gap. The owner holds a long-term Ed25519 keypair. At
embed time it signs a canonical claim binding the watermark UUID, the message
and a timestamp to the owner's public key. Verification needs only the public
key, which the owner can publish freely. The chain becomes:

    pixels --(robust DCT)--> UUID --(this signature)--> owner's signed assertion

So "prove I made this" reduces to "the holder of public key K signed, at time T,
that watermark X carries message M" — and the watermark ties X to the pixels.

Scope, stated honestly:
  * The signature is non-repudiable *relative to the keyholder*. It does not, by
    itself, stop someone re-embedding a fresh watermark into a copy and signing
    it with their own key. Precedence between competing claims needs a trusted
    timestamp anchor (RFC 3161 / a public ledger / C2PA); ``created`` here is
    self-asserted until such an anchor is attached. See ``signed_time``.
  * The identity private key is the owner's ROOT secret. Unlike the registry
    key it is meant to be portable and backed up (you may sign on more than one
    machine), so it is not machine-bound in a way that would trap it. It is
    wrapped at rest against casual file theft and can be exported password-
    protected for backup — see ``export_identity`` / ``import_identity``.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
from typing import Any, Dict, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from ..exceptions import AuthorshipError

CLAIM_VERSION = 1
ALG = "ed25519"


# ------------------------------------------------------------- serialization

def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def public_key_bytes(priv: Ed25519PrivateKey) -> bytes:
    return priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def public_fingerprint(pub_bytes: bytes) -> str:
    """Short, stable, human-quotable identity id derived from the public key."""
    return hashlib.sha256(pub_bytes).hexdigest()[:16]


def canonical_claim(*, watermark_id: str, message: str, created: str,
                    pubkey_b64: str) -> bytes:
    """Deterministic bytes to sign/verify.

    Sorted keys + compact separators, so encoder and verifier serialize the same
    claim to the same bytes regardless of dict ordering.
    """
    obj = {
        "v": CLAIM_VERSION,
        "alg": ALG,
        "watermark_id": watermark_id,
        "message": message,
        "created": created,
        "pubkey": pubkey_b64,
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


# --------------------------------------------------------------- sign/verify

def sign_claim(priv: Ed25519PrivateKey, *, watermark_id: str, message: str,
               created: Optional[str] = None) -> Dict[str, Any]:
    """Produce the signature record stored alongside a registry entry."""
    created = created or signed_time()
    pub_b64 = _b64e(public_key_bytes(priv))
    claim = canonical_claim(watermark_id=watermark_id, message=message,
                            created=created, pubkey_b64=pub_b64)
    signature = priv.sign(claim)
    return {
        "v": CLAIM_VERSION,
        "alg": ALG,
        "created": created,
        "pubkey": pub_b64,
        "fingerprint": public_fingerprint(public_key_bytes(priv)),
        "signature": _b64e(signature),
    }


class VerifyResult:
    __slots__ = ("valid", "signer", "created", "reason")

    def __init__(self, valid: bool, *, signer: Optional[str] = None,
                 created: Optional[str] = None, reason: Optional[str] = None):
        self.valid = valid
        self.signer = signer
        self.created = created
        self.reason = reason

    def as_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"valid": self.valid}
        if self.signer:
            d["signer"] = self.signer
        if self.created:
            d["created"] = self.created
        if self.reason:
            d["reason"] = self.reason
        return d


def verify_claim(record: Optional[Dict[str, Any]], *, watermark_id: str,
                 message: str) -> VerifyResult:
    """Verify a stored signature record against the recovered id + message.

    Rebuilds the exact claim from the record's own pubkey/created and the caller-
    supplied watermark_id/message. If either the message or the id was altered
    after signing, the reconstructed claim differs and the signature fails.
    """
    if not record:
        return VerifyResult(False, reason="unsigned")
    try:
        pub_b64 = record["pubkey"]
        created = record["created"]
        sig = _b64d(record["signature"])
        pub = Ed25519PublicKey.from_public_bytes(_b64d(pub_b64))
    except (KeyError, ValueError, TypeError) as exc:
        return VerifyResult(False, reason=f"malformed: {exc}")

    claim = canonical_claim(watermark_id=watermark_id, message=message,
                            created=created, pubkey_b64=pub_b64)
    try:
        pub.verify(sig, claim)
    except InvalidSignature:
        return VerifyResult(False, signer=record.get("fingerprint"),
                            created=created, reason="signature mismatch")
    return VerifyResult(True, signer=public_fingerprint(_b64d(pub_b64)),
                        created=created)


def signed_time() -> str:
    """UTC ISO-8601 timestamp embedded in the claim.

    Self-asserted: it proves the signer *claimed* this time, not that the time
    is true. A tamper-evident anchor (RFC 3161 token, public ledger, C2PA
    manifest time) can be layered on top later without changing this format.
    """
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------- identity at rest

def _wrap_key() -> bytes:
    from .keys import registry_master_key
    return registry_master_key(bind_machine=True)


def load_or_create_identity(*, create: bool = True) -> Optional[Ed25519PrivateKey]:
    """Load this installation's authorship key, generating one on first use.

    Wrapped at rest with the machine-bound local key, so lifting the file alone
    onto another box does not yield a usable signing key.
    """
    from ..paths import identity_key_path
    from .crypto import aead_decrypt, aead_encrypt, unpack_encrypted, pack_encrypted

    path = identity_key_path()
    if path.is_file():
        blob = path.read_bytes()
        try:
            nonce, ct = unpack_encrypted(blob)
            seed = aead_decrypt(_wrap_key(), nonce, ct, associated_data=b"stashpix-identity")
        except Exception as exc:
            raise AuthorshipError(key="error.identity_unwrap", detail=str(exc))
        return Ed25519PrivateKey.from_private_bytes(seed)

    if not create:
        return None

    priv = Ed25519PrivateKey.generate()
    seed = priv.private_bytes(serialization.Encoding.Raw,
                              serialization.PrivateFormat.Raw,
                              serialization.NoEncryption())
    nonce, ct = aead_encrypt(_wrap_key(), seed, associated_data=b"stashpix-identity")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pack_encrypted(nonce, ct))
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return priv


def identity_fingerprint(*, create: bool = False) -> Optional[str]:
    priv = load_or_create_identity(create=create)
    if priv is None:
        return None
    return public_fingerprint(public_key_bytes(priv))


def export_public_pem(priv: Ed25519PrivateKey) -> str:
    """The shareable public key — publish this so others can verify your claims."""
    return priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")


def export_identity(priv: Ed25519PrivateKey, password: str) -> bytes:
    """Password-encrypted PKCS8 for backup / moving the identity to another box.

    Portability is deliberate: this is the owner's root key, not a per-machine
    secret, so it must be recoverable. The password is what protects the export.
    """
    if not password:
        raise AuthorshipError(key="error.identity_export_password")
    return priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password.encode("utf-8")))


def import_identity(pem_bytes: bytes, password: str, *, overwrite: bool = False
                    ) -> Ed25519PrivateKey:
    """Load a password-encrypted PKCS8 identity and store it wrapped at rest."""
    from ..paths import identity_key_path
    from .crypto import aead_encrypt, pack_encrypted

    key = serialization.load_pem_private_key(pem_bytes, password=password.encode("utf-8"))
    if not isinstance(key, Ed25519PrivateKey):
        raise AuthorshipError(key="error.identity_import_type")

    path = identity_key_path()
    if path.is_file() and not overwrite:
        raise AuthorshipError(key="error.identity_exists")
    seed = key.private_bytes(serialization.Encoding.Raw,
                             serialization.PrivateFormat.Raw,
                             serialization.NoEncryption())
    nonce, ct = aead_encrypt(_wrap_key(), seed, associated_data=b"stashpix-identity")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pack_encrypted(nonce, ct))
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return key


__all__ = [
    "AuthorshipError",
    "CLAIM_VERSION",
    "ALG",
    "canonical_claim",
    "sign_claim",
    "verify_claim",
    "VerifyResult",
    "signed_time",
    "public_key_bytes",
    "public_fingerprint",
    "load_or_create_identity",
    "identity_fingerprint",
    "export_public_pem",
    "export_identity",
    "import_identity",
]
