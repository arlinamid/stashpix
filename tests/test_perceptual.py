"""Perceptual hash and registry ranking tests."""

from PIL import Image

from stashpix.core.perceptual import dhash_hex, edge_hash_hex, hamming_hex, phash_hex
from stashpix.registry import Registry


def test_phash_stable(noise_path):
    img = Image.open(noise_path).convert("RGB")
    assert phash_hex(img) == phash_hex(img)
    assert dhash_hex(img) == dhash_hex(img)


def test_edge_hash_stable(noise_path):
    img = Image.open(noise_path).convert("RGB")
    assert edge_hash_hex(img) == edge_hash_hex(img)


def test_hamming_identical_zero(noise_path):
    h = phash_hex(Image.open(noise_path).convert("RGB"))
    assert hamming_hex(h, h) == 0


def test_ranked_reference_ids(tmp_path, noise_path):
    reg = Registry(str(tmp_path / "r.json"))
    img_a = Image.open(noise_path).convert("RGB")
    img_b = img_a.resize((img_a.width - 20, img_a.height - 10))
    reg.add("aaa", "one")
    reg.add("bbb", "two")
    reg.save_reference("aaa", img_a)
    reg.save_reference("bbb", img_b)
    ranked = reg.ranked_reference_ids(img_a, top_k=2)
    assert ranked[0][0] == "aaa"
    assert ranked[0][1] <= ranked[1][1]


def test_registry_encrypted_at_rest(tmp_path):
    reg = Registry(str(tmp_path / "r.json"))
    reg.add("deadbeef", "secret")
    raw = (tmp_path / "r.json").read_text(encoding="utf-8")
    assert "secret" not in raw
    assert reg.message_for("deadbeef") == "secret"
