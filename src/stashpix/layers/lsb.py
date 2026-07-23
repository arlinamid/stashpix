"""LSB layer — Reed-Solomon + key-based spreading + AEAD + redundancy.

Carries the FULL message in the spatial least-significant bits. Survives
repaint thanks to spreading + RS + copies but not JPEG/resize/crop (the
permutation is image-size dependent).
"""

from __future__ import annotations

import random
from collections import Counter
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image

from ..core.base import Layer, EmbedOutcome, LayerResult
from ..core.coding import (
    RSCodec,
    ReedSolomonError,
    bits_to_int,
    int_to_bits,
    bytes_to_bits,
    bits_to_bytes,
    hamming_encode_bits,
    hamming_decode_bits,
)
from ..core.crypto import aead_decrypt, aead_encrypt, pack_encrypted, unpack_encrypted
from ..core.keys import (
    CONTENT_SALT_BYTES,
    derive_content_key,
    derive_seed,
    new_content_salt,
)
from ..exceptions import CapacityError, DecodeError, SelfVerifyError, StegoError

# v3 prefixes the payload with a fresh random salt so the content key is no
# longer derived from the password alone. v2 and earlier used one hardcoded salt
# for every image ever produced; those payloads are rejected rather than read.
LSB_FORMAT_VERSION = 3
HEADER_REPEATS_BASE = 25
LEN_FIELD_BITS = 32
NSYM_FIELD_BITS = 8
COPIES_FIELD_BITS = 8
VERSION_FIELD_BITS = 8
HEADER_RAW_BITS = LEN_FIELD_BITS + NSYM_FIELD_BITS + COPIES_FIELD_BITS + VERSION_FIELD_BITS
HEADER_ENC_BITS = (HEADER_RAW_BITS // 4) * 7
if HEADER_RAW_BITS % 4:
    HEADER_ENC_BITS += 7


def header_repeats(capacity_bits: int) -> int:
    extra = min(capacity_bits // 15000, 1024)
    reps = HEADER_REPEATS_BASE + extra
    if reps % 2 == 0:
        reps += 1
    return reps


def _build_permutation(capacity_bits: int, seed) -> List[int]:
    rng = random.Random(seed)
    perm = list(range(capacity_bits))
    rng.shuffle(perm)
    return perm


def _build_header_bits(rs_len_bytes: int, nsym: int, copies: int, reps: int) -> List[int]:
    raw = (
        int_to_bits(rs_len_bytes, LEN_FIELD_BITS)
        + int_to_bits(nsym, NSYM_FIELD_BITS)
        + int_to_bits(copies, COPIES_FIELD_BITS)
        + int_to_bits(LSB_FORMAT_VERSION, VERSION_FIELD_BITS)
    )
    return hamming_encode_bits(raw) * reps


def _read_header(header_bits: List[int], reps: int) -> Tuple[int, int, int, int, int]:
    chunks = [header_bits[i * HEADER_ENC_BITS:(i + 1) * HEADER_ENC_BITS]
              for i in range(reps)]
    majority = []
    for i in range(HEADER_ENC_BITS):
        ones = sum(chunk[i] for chunk in chunks)
        majority.append(1 if ones * 2 > reps else 0)

    candidates = []
    raw = hamming_decode_bits(majority)
    if len(raw) >= HEADER_RAW_BITS:
        candidates.append(_parse_header_raw(raw))
    if not candidates:
        for chunk in chunks:
            raw_c = hamming_decode_bits(chunk)
            if len(raw_c) >= HEADER_RAW_BITS:
                candidates.append(_parse_header_raw(raw_c))
    if not candidates:
        raise DecodeError(key="error.decode_header")

    parsed, votes = Counter(candidates).most_common(1)[0]
    rs_len, nsym, copies, version = parsed
    return rs_len, nsym, copies, version, votes


def _parse_header_raw(raw: List[int]) -> Tuple[int, int, int, int]:
    rs_len = bits_to_int(raw[:LEN_FIELD_BITS])
    nsym = bits_to_int(raw[LEN_FIELD_BITS:LEN_FIELD_BITS + NSYM_FIELD_BITS])
    copies = bits_to_int(raw[LEN_FIELD_BITS + NSYM_FIELD_BITS:
                              LEN_FIELD_BITS + NSYM_FIELD_BITS + COPIES_FIELD_BITS])
    version = bits_to_int(raw[LEN_FIELD_BITS + NSYM_FIELD_BITS + COPIES_FIELD_BITS:HEADER_RAW_BITS])
    return rs_len, nsym, copies, version


class LsbLayer(Layer):
    """The spatial-domain LSB layer (carries the full message)."""

    name_key = "layer.lsb.name"

    def embed(self, image: Image.Image, message: str, config) -> EmbedOutcome:
        nsym = config.lsb_nsym
        copies = config.lsb_copies
        if not (1 <= nsym <= 254):
            raise StegoError(key="error.nsym_range")
        if not (1 <= copies <= 255):
            raise StegoError(key="error.copies_range")

        arr = np.asarray(image.convert("RGB"), dtype=np.uint8).copy()
        height, width, _ = arr.shape
        capacity_bits = width * height * 3

        rs_encoded = RSCodec(nsym).encode(message.encode("utf-8"))
        rs_len = len(rs_encoded)
        # Fresh salt per embed: the same message under the same password must not
        # produce the same ciphertext twice, and precomputation against a fixed
        # salt must not help. The salt is plaintext in the payload by design.
        salt = new_content_salt()
        sym_key = derive_content_key(config.key, salt)
        nonce, ciphertext = aead_encrypt(
            sym_key, rs_encoded,
            associated_data=f"v{LSB_FORMAT_VERSION}:{rs_len}:{nsym}:{copies}".encode())
        payload_bytes = salt + pack_encrypted(nonce, ciphertext)
        payload_bits = bytes_to_bits(payload_bytes)
        L = len(payload_bits)

        reps = header_repeats(capacity_bits)
        header_bits = _build_header_bits(rs_len, nsym, copies, reps)
        header_total = len(header_bits)

        total_needed = header_total + copies * L
        if total_needed > capacity_bits:
            max_copies = max(0, (capacity_bits - header_total) // L) if L else 0
            raise CapacityError(needed=total_needed, available=capacity_bits,
                                max_copies=max_copies)

        all_bits = header_bits + payload_bits * copies

        seed = derive_seed(config.key)
        perm = np.asarray(_build_permutation(capacity_bits, seed), dtype=np.int64)
        bits = np.asarray(all_bits, dtype=np.uint8)

        positions = perm[:len(all_bits)]
        flat = arr.reshape(-1)
        flat[positions] = (flat[positions] & np.uint8(0xFE)) | bits

        out_img = Image.fromarray(arr, "RGB")
        info = {"rs_len": rs_len, "nsym": nsym, "copies": copies, "format": LSB_FORMAT_VERSION,
                "used_bits": len(all_bits), "capacity_bits": capacity_bits}

        if config.lsb_self_verify:
            try:
                result = self.extract(out_img, config)
            except StegoError as e:
                raise SelfVerifyError(key="error.self_verify_read", detail=str(e))
            if result is None or result.message != message:
                raise SelfVerifyError()
            info["self_verify"] = result.info

        return EmbedOutcome(image=out_img, info=info)

    def extract(self, image: Image.Image, config) -> Optional[LayerResult]:
        arr = np.asarray(image.convert("RGB"), dtype=np.uint8)
        height, width, _ = arr.shape
        capacity_bits = width * height * 3
        flat = arr.reshape(-1)

        seed = derive_seed(config.key)
        perm = np.asarray(_build_permutation(capacity_bits, seed), dtype=np.int64)

        reps = header_repeats(capacity_bits)
        probe_len = HEADER_ENC_BITS * reps
        if probe_len > capacity_bits:
            raise DecodeError(key="error.decode_header")

        header_bits = (flat[perm[:probe_len]] & 1).tolist()
        rs_len, nsym, copies, version, header_votes = _read_header(header_bits, reps)
        if version != LSB_FORMAT_VERSION:
            raise DecodeError(key="error.decode_params")

        aad = f"v{version}:{rs_len}:{nsym}:{copies}".encode()

        # Probe payload length from first copy (encrypted blob size varies with RS)
        # We need rs_len to know plaintext size but ciphertext length = rs_len + overhead
        # Actually we stored rs_len as RS-encoded length; encrypted size unknown without reading.
        # Embed side: payload is fixed per embed — read until we have enough bits for one copy.
        # Strategy: read max possible from first copy slot using remaining capacity.
        remaining = capacity_bits - probe_len
        if copies <= 0 or remaining <= 0:
            raise DecodeError(key="error.decode_params")

        # Binary search copy length is hard; store encrypted byte length in rs_len field? 
        # rs_len IS the RS byte length; encrypted = nonce(12)+ct(rs_len+16 tag) approx
        from ..core.crypto import _NONCE_LEN, _TAG_OVERHEAD
        enc_byte_len = CONTENT_SALT_BYTES + _NONCE_LEN + rs_len + _TAG_OVERHEAD
        L = enc_byte_len * 8

        if probe_len + copies * L > capacity_bits:
            raise DecodeError(key="error.decode_params")

        copy_bit_arrays = []
        for c in range(copies):
            start = probe_len + c * L
            positions = perm[start:start + L]
            copy_bit_arrays.append((flat[positions] & 1).astype(np.uint8))

        stack = np.vstack(copy_bit_arrays)
        ones = stack.sum(axis=0)
        majority_bits = (ones * 2 > copies).astype(np.uint8)
        disagreements = int(np.count_nonzero((ones != 0) & (ones != copies)))

        def try_decrypt(bits) -> Optional[Tuple[bytes, int]]:
            try:
                blob = bits_to_bytes(bits.tolist())
                # The salt is carried in the clear ahead of the AEAD blob, so a
                # corrupted salt simply yields a key that fails authentication.
                salt, blob = blob[:CONTENT_SALT_BYTES], blob[CONTENT_SALT_BYTES:]
                sym_key = derive_content_key(config.key, salt)
                nonce, ciphertext = unpack_encrypted(blob)
                rs_blob = aead_decrypt(sym_key, nonce, ciphertext, associated_data=aad)
                if len(rs_blob) != rs_len:
                    return None
                rsc = RSCodec(nsym)
                decoded, _full, errata = rsc.decode(rs_blob)
                return bytes(decoded), len(errata)
            except Exception:
                return None

        used_source = "voted"
        rs_errors = 0
        message_bytes = None
        res = try_decrypt(majority_bits)
        if res is not None:
            message_bytes, rs_errors = res
        else:
            for bits in copy_bit_arrays:
                res = try_decrypt(bits)
                if res is not None:
                    message_bytes, rs_errors = res
                    used_source = "single copy"
                    break

        if message_bytes is None:
            raise DecodeError(key="error.decode_rs")

        try:
            message = message_bytes.decode("utf-8")
        except UnicodeDecodeError as e:
            raise DecodeError(key="error.decode_utf8", detail=str(e))

        info = {
            "header_votes": header_votes,
            "rs_nsym": nsym,
            "copies_total": copies,
            "format": version,
            "bit_disagreements": disagreements,
            "rs_errors_corrected": rs_errors,
            "recovery_source": used_source,
        }
        return LayerResult(message=message, layer_key=self.name_key, info=info)


__all__ = ["LsbLayer", "header_repeats", "HEADER_ENC_BITS", "LSB_FORMAT_VERSION"]
