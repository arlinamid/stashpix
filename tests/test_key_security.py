"""Key derivation guarantees.

Before v1.5.0 two things were wrong here. A missing key silently fell back to the
constant seed ``DEFAULT_SEED = 1337``, so an unkeyed embed looked encrypted but
anyone could read it. And ``derive_key_bytes`` salted every derivation with one
hardcoded constant, ``sha256("stashpix:salt:v1")``, so a given password mapped to
one globally fixed key -- precomputable once, reusable against every image the
tool had ever produced.
"""

from __future__ import annotations

import os

import numpy as np
import pytest
from PIL import Image

from stashpix.config import EmbedConfig, ExtractConfig
from stashpix.core.keys import (
    CONTENT_SALT_BYTES,
    derive_content_key,
    derive_seed,
    machine_fingerprint,
    new_content_salt,
    require_key,
)
from stashpix.exceptions import StegoError

MSG = "Key security probe"
KEY = "correct horse battery staple"


# ------------------------------------------------------------ mandatory key

@pytest.mark.parametrize("bad", [None, "", "   ", "\t\n"])
def test_embed_config_rejects_missing_key(bad):
    with pytest.raises(StegoError):
        EmbedConfig(key=bad)


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_extract_config_rejects_missing_key(bad):
    with pytest.raises(StegoError):
        ExtractConfig(key=bad)


def test_require_key_rejects_none():
    with pytest.raises(StegoError):
        require_key(None)


def test_require_key_accepts_int_and_text():
    assert require_key(1337) == 1337
    assert require_key("pw") == "pw"


def test_no_default_seed_constant_remains():
    """The 1337 fallback must be gone, not merely unused."""
    import stashpix.core.keys as keys

    assert not hasattr(keys, "DEFAULT_SEED")
    assert not hasattr(keys, "derive_key_bytes")


# --------------------------------------------------------- per-message salt

def test_content_salt_is_random_and_long_enough():
    salts = {new_content_salt() for _ in range(32)}
    assert len(salts) == 32
    assert all(len(s) == CONTENT_SALT_BYTES for s in salts)


def test_same_password_different_salt_yields_different_key():
    a = derive_content_key(KEY, new_content_salt())
    b = derive_content_key(KEY, new_content_salt())
    assert a != b
    assert len(a) == 32


def test_content_key_is_reproducible_from_the_same_salt():
    """The decoder recovers the salt from the payload and must land on the key."""
    salt = new_content_salt()
    assert derive_content_key(KEY, salt) == derive_content_key(KEY, salt)


def test_content_key_rejects_a_short_salt():
    with pytest.raises(ValueError):
        derive_content_key(KEY, b"tooshort")


def test_content_key_requires_a_key():
    with pytest.raises(StegoError):
        derive_content_key(None, new_content_salt())


def test_repeated_embeds_do_not_repeat_ciphertext(engine, tmp_path, noise_path):
    """Same cover, same message, same password -- the bits must still differ."""
    cover = Image.open(noise_path).convert("RGB")
    outs = []
    for i in range(2):
        out = tmp_path / f"a{i}.png"
        engine.embed(cover, MSG, EmbedConfig(key=KEY, enable_robust=False))[0].save(out)
        outs.append(np.asarray(Image.open(out).convert("RGB"), dtype=np.uint8) & 1)
    assert not np.array_equal(outs[0], outs[1]), "identical LSB planes: salt not applied"


# ------------------------------------------------------------- portability

def test_seed_is_portable_across_machines():
    """The permutation seed must not depend on the machine.

    A machine-bound seed would make an image embedded on one computer
    unreadable on another with the correct password, which defeats the product.
    """
    first = derive_seed(KEY)
    assert derive_seed(KEY) == first
    assert isinstance(first, int)


def test_seed_does_not_mix_in_the_machine_fingerprint(monkeypatch):
    before = derive_seed(KEY)
    monkeypatch.setattr("stashpix.core.keys.machine_fingerprint",
                        lambda: b"\x00" * 32)
    assert derive_seed(KEY) == before


def test_content_key_does_not_mix_in_the_machine_fingerprint(monkeypatch):
    salt = new_content_salt()
    before = derive_content_key(KEY, salt)
    monkeypatch.setattr("stashpix.core.keys.machine_fingerprint",
                        lambda: b"\xff" * 32)
    assert derive_content_key(KEY, salt) == before


def test_different_passwords_give_different_seeds():
    assert derive_seed("alpha") != derive_seed("beta")


# ------------------------------------------------------- wrong key rejected

def test_wrong_key_cannot_read_the_message(engine, tmp_path, photo_path):
    out = tmp_path / "stego.png"
    engine.embed_file(photo_path, MSG, str(out), EmbedConfig(key=KEY))
    msg, info = engine.extract_file(str(out), ExtractConfig(key="wrong password"))
    assert msg is None
    assert info.get("layer_key") is None


# ------------------------------------------------------ machine-bound local

def test_machine_fingerprint_is_stable_and_opaque():
    a = machine_fingerprint()
    assert a == machine_fingerprint()
    assert len(a) == 32


def test_registry_is_bound_to_this_machine(tmp_path, monkeypatch):
    """A copied key file alone must not decrypt a copied registry."""
    from stashpix.registry import Registry

    monkeypatch.setenv("STASHPIX_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("STASHPIX_REGISTRY_KEY", raising=False)

    reg = Registry(str(tmp_path / "r.json"))
    reg.add("deadbeef", "secret note")
    assert reg.message_for("deadbeef") == "secret note"

    # Same key file, different machine identity.
    monkeypatch.setattr("stashpix.core.keys.machine_fingerprint",
                        lambda: b"\x01" * 32)
    with pytest.raises(Exception):
        Registry(str(tmp_path / "r.json")).all()


def test_legacy_unbound_registry_still_readable(tmp_path, monkeypatch):
    """v1 registries predate machine binding and must survive the upgrade."""
    import json

    from stashpix.core.crypto import aead_encrypt, b64_encode
    from stashpix.core.keys import registry_master_key
    from stashpix.registry.store import LEGACY_REGISTRY_FORMAT, Registry

    monkeypatch.setenv("STASHPIX_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("STASHPIX_REGISTRY_KEY", raising=False)

    payload = {"cafe1234": {"message": "from v1.4.0", "meta": {}}}
    key = registry_master_key(bind_machine=False)
    nonce, ct = aead_encrypt(key, json.dumps(payload).encode(),
                             associated_data=LEGACY_REGISTRY_FORMAT.encode())
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({
        "format": LEGACY_REGISTRY_FORMAT,
        "nonce": b64_encode(nonce),
        "ciphertext": b64_encode(ct),
    }), encoding="utf-8")

    assert Registry(str(path)).message_for("cafe1234") == "from v1.4.0"


def test_registry_rewrites_legacy_as_bound(tmp_path, monkeypatch):
    """Writing a legacy registry must upgrade it to the machine-bound format."""
    import json

    from stashpix.core.crypto import aead_encrypt, b64_encode
    from stashpix.core.keys import registry_master_key
    from stashpix.registry.store import (
        LEGACY_REGISTRY_FORMAT, REGISTRY_FORMAT, Registry,
    )

    monkeypatch.setenv("STASHPIX_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("STASHPIX_REGISTRY_KEY", raising=False)

    key = registry_master_key(bind_machine=False)
    nonce, ct = aead_encrypt(key, json.dumps({"aa": {"message": "old"}}).encode(),
                             associated_data=LEGACY_REGISTRY_FORMAT.encode())
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({
        "format": LEGACY_REGISTRY_FORMAT,
        "nonce": b64_encode(nonce),
        "ciphertext": b64_encode(ct),
    }), encoding="utf-8")

    reg = Registry(str(path))
    reg.add("bb", "new")
    assert json.loads(path.read_text(encoding="utf-8"))["format"] == REGISTRY_FORMAT
    assert reg.message_for("aa") == "old"
    assert reg.message_for("bb") == "new"


# ------------------------------------------------------- format versioning

def test_lsb_format_version_bumped_past_the_fixed_salt_era():
    from stashpix.layers.lsb import LSB_FORMAT_VERSION

    assert LSB_FORMAT_VERSION >= 3


def test_old_format_payload_is_rejected(engine, tmp_path, noise_path):
    """A v2 header must not decode -- its key came from the hardcoded salt."""
    from stashpix.layers import lsb as lsb_mod

    cover = Image.open(noise_path).convert("RGB")
    monkey_version = 2
    original = lsb_mod.LSB_FORMAT_VERSION
    try:
        lsb_mod.LSB_FORMAT_VERSION = monkey_version
        stego, _ = engine.embed(cover, MSG, EmbedConfig(key=KEY, enable_robust=False))
    finally:
        lsb_mod.LSB_FORMAT_VERSION = original

    msg, info = engine.extract(stego, ExtractConfig(key=KEY))
    assert msg is None
    assert "lsb_failed" in info
