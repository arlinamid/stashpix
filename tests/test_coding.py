"""Unit tests for coding-theory primitives."""

from stashpix.core.coding import (
    bytes_to_bits,
    bits_to_bytes,
    int_to_bits,
    bits_to_int,
    hamming_encode_bits,
    hamming_decode_bits,
    keystream_bits,
)


def test_bytes_bits_roundtrip():
    data = b"hello \xc3\xa9"
    assert bits_to_bytes(bytes_to_bits(data)) == data


def test_int_bits_roundtrip():
    assert bits_to_int(int_to_bits(1337, 16)) == 1337


def test_hamming_corrects_single_bit():
    raw = [1, 0, 1, 1, 0, 0, 1, 0]
    enc = hamming_encode_bits(raw)
    enc[2] ^= 1  # flip one bit
    dec = hamming_decode_bits(enc)
    assert dec[:len(raw)] == raw


def test_keystream_deterministic_and_prefix_stable():
    a = keystream_bits("k", 100)
    b = keystream_bits("k", 50)
    assert a[:50] == b            # bit i depends only on i
    assert keystream_bits("other", 50) != b
