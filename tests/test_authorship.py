"""Ed25519 authorship signatures — the "prove I made this" backbone.

The robust watermark ties a UUID to the pixels; these signatures tie that UUID
to the owner's key at a stated time. A verifier with the public key can then
confirm "the holder of key K asserted watermark X carries message M", and the
watermark confirms X is in the pixels.

What these tests pin down:
  * a genuine claim verifies; a tampered message or id does not;
  * a claim signed by a different key does not verify against the owner's key;
  * the identity persists, exports and re-imports, and is bound to the machine
    at rest;
  * the whole thing surfaces through engine.embed / engine.extract.
"""

from __future__ import annotations

import os

import pytest
from PIL import Image

from stashpix.config import EmbedConfig, ExtractConfig
from stashpix.core import authorship
from stashpix.exceptions import AuthorshipError

MSG = "This image is mine — 2026"
KEY = "embed-key"


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("STASHPIX_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("STASHPIX_REGISTRY_KEY", raising=False)
    return tmp_path


# ------------------------------------------------------------- claim crypto

def test_claim_roundtrip_verifies():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    k = Ed25519PrivateKey.generate()
    rec = authorship.sign_claim(k, watermark_id="abc123", message=MSG)
    res = authorship.verify_claim(rec, watermark_id="abc123", message=MSG)
    assert res.valid
    assert res.signer == rec["fingerprint"]
    assert res.created == rec["created"]


def test_tampered_message_fails():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    rec = authorship.sign_claim(Ed25519PrivateKey.generate(),
                                watermark_id="abc123", message=MSG)
    res = authorship.verify_claim(rec, watermark_id="abc123", message="not the message")
    assert not res.valid
    assert res.reason == "signature mismatch"


def test_tampered_id_fails():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    rec = authorship.sign_claim(Ed25519PrivateKey.generate(),
                                watermark_id="abc123", message=MSG)
    assert not authorship.verify_claim(rec, watermark_id="deadbeef", message=MSG).valid


def test_forged_signature_from_other_key_fails():
    """A claim re-signed by an attacker's key must not verify as the owner's.

    The verifier binds identity to the pubkey inside the record, so an attacker
    can only ever produce a claim under *their own* fingerprint, never the
    owner's.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    owner = Ed25519PrivateKey.generate()
    attacker = Ed25519PrivateKey.generate()

    owner_rec = authorship.sign_claim(owner, watermark_id="x", message=MSG)
    attacker_rec = authorship.sign_claim(attacker, watermark_id="x", message=MSG)

    assert authorship.verify_claim(owner_rec, watermark_id="x", message=MSG).signer \
        != authorship.verify_claim(attacker_rec, watermark_id="x", message=MSG).signer

    # Splice the owner's fingerprint onto the attacker's signature -> must fail.
    forged = dict(attacker_rec)
    forged["pubkey"] = owner_rec["pubkey"]
    assert not authorship.verify_claim(forged, watermark_id="x", message=MSG).valid


def test_unsigned_record_reports_unsigned():
    res = authorship.verify_claim(None, watermark_id="x", message=MSG)
    assert not res.valid
    assert res.reason == "unsigned"


def test_fingerprint_is_stable_and_short():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    k = Ed25519PrivateKey.generate()
    pub = authorship.public_key_bytes(k)
    assert authorship.public_fingerprint(pub) == authorship.public_fingerprint(pub)
    assert len(authorship.public_fingerprint(pub)) == 16


# ------------------------------------------------------------- identity mgmt

def test_identity_persists_across_loads(home):
    a = authorship.load_or_create_identity(create=True)
    fp1 = authorship.public_fingerprint(authorship.public_key_bytes(a))
    b = authorship.load_or_create_identity(create=True)
    fp2 = authorship.public_fingerprint(authorship.public_key_bytes(b))
    assert fp1 == fp2


def test_identity_is_wrapped_at_rest(home):
    """The stored file must not be the raw 32-byte seed."""
    from stashpix.paths import identity_key_path
    priv = authorship.load_or_create_identity(create=True)
    raw = priv.private_bytes(
        __import__("cryptography.hazmat.primitives.serialization",
                   fromlist=["Encoding"]).Encoding.Raw,
        __import__("cryptography.hazmat.primitives.serialization",
                   fromlist=["PrivateFormat"]).PrivateFormat.Raw,
        __import__("cryptography.hazmat.primitives.serialization",
                   fromlist=["NoEncryption"]).NoEncryption())
    on_disk = identity_key_path().read_bytes()
    assert raw not in on_disk
    assert len(on_disk) > 32          # nonce + ciphertext + tag


def test_identity_at_rest_is_machine_bound(home, monkeypatch):
    authorship.load_or_create_identity(create=True)
    monkeypatch.setattr("stashpix.core.keys.machine_fingerprint", lambda: b"\x02" * 32)
    with pytest.raises(AuthorshipError):
        authorship.load_or_create_identity(create=False)


def test_export_import_roundtrip(home, tmp_path):
    priv = authorship.load_or_create_identity(create=True)
    fp = authorship.public_fingerprint(authorship.public_key_bytes(priv))
    pem = authorship.export_identity(priv, "backup-pass")

    # Fresh home: import must restore the same identity.
    (tmp_path / "home2").mkdir()
    os.environ["STASHPIX_HOME"] = str(tmp_path / "home2")
    imported = authorship.import_identity(pem, "backup-pass")
    assert authorship.public_fingerprint(authorship.public_key_bytes(imported)) == fp


def test_export_requires_password(home):
    priv = authorship.load_or_create_identity(create=True)
    with pytest.raises(AuthorshipError):
        authorship.export_identity(priv, "")


def test_import_wrong_password_fails(home, tmp_path):
    priv = authorship.load_or_create_identity(create=True)
    pem = authorship.export_identity(priv, "right")
    with pytest.raises(Exception):
        authorship.import_identity(pem, "wrong", overwrite=True)


# --------------------------------------------------------------- end to end

def test_embed_signs_and_extract_verifies(home, photo_path, tmp_path):
    from stashpix.engine import StegoEngine
    from stashpix.registry import Registry

    reg = Registry(str(tmp_path / "r.json"))
    engine = StegoEngine(registry=reg)
    out = tmp_path / "stego.png"
    res = engine.embed_file(photo_path, MSG, str(out), EmbedConfig(key=KEY))
    assert "signature" in res.info["layers"]
    assert res.info.get("signed_by")

    msg, info = engine.extract_file(str(out), ExtractConfig(key=KEY))
    assert msg == MSG
    assert info["authorship"]["valid"] is True
    assert info["authorship"]["signer"] == res.info["signed_by"]


def test_extract_flags_a_registry_message_tampered_after_signing(home, photo_path, tmp_path):
    """If someone edits the stored message but not the signature, verify fails."""
    from stashpix.engine import StegoEngine
    from stashpix.registry import Registry

    reg = Registry(str(tmp_path / "r.json"))
    engine = StegoEngine(registry=reg)
    out = tmp_path / "stego.png"
    res = engine.embed_file(photo_path, MSG, str(out), EmbedConfig(key=KEY))

    data = reg._load_plain()
    data[res.robust_id]["message"] = "forged ownership note"
    reg._save_plain(data)

    msg, info = engine.extract_file(str(out), ExtractConfig(key=KEY))
    assert info["authorship"]["valid"] is False


def test_signing_can_be_disabled(home, photo_path, tmp_path):
    from stashpix.engine import StegoEngine
    from stashpix.registry import Registry

    reg = Registry(str(tmp_path / "r.json"))
    engine = StegoEngine(registry=reg)
    out = tmp_path / "stego.png"
    res = engine.embed_file(photo_path, MSG, str(out), EmbedConfig(key=KEY, sign=False))
    assert "signature" not in res.info["layers"]

    msg, info = engine.extract_file(str(out), ExtractConfig(key=KEY))
    assert msg == MSG
    assert info["authorship"]["valid"] is False
    assert info["authorship"]["reason"] == "unsigned"
