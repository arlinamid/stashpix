"""LSB layer — Reed-Solomon + key-based spreading + XOR-whitening + redundancy.

Carries the FULL message in the spatial least-significant bits. Survives
crop/repaint (thanks to spreading + RS + copies) but not JPEG/resize.
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
    keystream_bits,
)
from ..core.keys import derive_seed
from ..exceptions import CapacityError, DecodeError, SelfVerifyError, StegoError

# --- Self-describing header layout ---------------------------------------
HEADER_REPEATS_BASE = 25
LEN_FIELD_BITS = 32
NSYM_FIELD_BITS = 8
COPIES_FIELD_BITS = 8
HEADER_RAW_BITS = LEN_FIELD_BITS + NSYM_FIELD_BITS + COPIES_FIELD_BITS  # 48
HEADER_ENC_BITS = (HEADER_RAW_BITS // 4) * 7  # 84


def header_repeats(capacity_bits: int) -> int:
    """Capacity-proportional header replication (odd, for clean majority vote)."""
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
    raw = (int_to_bits(rs_len_bytes, LEN_FIELD_BITS)
           + int_to_bits(nsym, NSYM_FIELD_BITS)
           + int_to_bits(copies, COPIES_FIELD_BITS))
    return hamming_encode_bits(raw) * reps


def _read_header(header_bits: List[int], reps: int) -> Tuple[int, int, int, int]:
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

    (rs_len, nsym, copies), votes = Counter(candidates).most_common(1)[0]
    return rs_len, nsym, copies, votes


def _parse_header_raw(raw: List[int]) -> Tuple[int, int, int]:
    rs_len = bits_to_int(raw[:LEN_FIELD_BITS])
    nsym = bits_to_int(raw[LEN_FIELD_BITS:LEN_FIELD_BITS + NSYM_FIELD_BITS])
    copies = bits_to_int(raw[LEN_FIELD_BITS + NSYM_FIELD_BITS:HEADER_RAW_BITS])
    return rs_len, nsym, copies


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
        L = rs_len * 8

        reps = header_repeats(capacity_bits)
        header_bits = _build_header_bits(rs_len, nsym, copies, reps)
        header_total = len(header_bits)

        total_needed = header_total + copies * L
        if total_needed > capacity_bits:
            max_copies = max(0, (capacity_bits - header_total) // L) if L else 0
            raise CapacityError(needed=total_needed, available=capacity_bits,
                                max_copies=max_copies)

        payload_one = bytes_to_bits(rs_encoded)
        all_bits = header_bits + payload_one * copies

        seed = derive_seed(config.key)
        perm = np.asarray(_build_permutation(capacity_bits, seed), dtype=np.int64)
        keystream = np.asarray(keystream_bits(seed, len(all_bits)), dtype=np.uint8)
        bits = np.asarray(all_bits, dtype=np.uint8) ^ keystream

        positions = perm[:len(all_bits)]
        flat = arr.reshape(-1)
        flat[positions] = (flat[positions] & np.uint8(0xFE)) | bits

        out_img = Image.fromarray(arr, "RGB")
        info = {"rs_len": rs_len, "nsym": nsym, "copies": copies,
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

        ks = np.asarray(keystream_bits(seed, probe_len), dtype=np.uint8)
        header_bits = ((flat[perm[:probe_len]] & 1) ^ ks).tolist()
        rs_len, nsym, copies, header_votes = _read_header(header_bits, reps)

        L = rs_len * 8
        if rs_len <= 0 or nsym <= 0 or copies <= 0 or probe_len + copies * L > capacity_bits:
            raise DecodeError(key="error.decode_params")

        full_len = probe_len + copies * L
        ks_full = np.asarray(keystream_bits(seed, full_len), dtype=np.uint8)

        copy_bit_arrays = []
        for c in range(copies):
            start = probe_len + c * L
            positions = perm[start:start + L]
            arr_bits = (flat[positions] & 1) ^ ks_full[start:start + L]
            copy_bit_arrays.append(arr_bits)

        stack = np.vstack(copy_bit_arrays)
        ones = stack.sum(axis=0)
        majority_bits = (ones * 2 > copies).astype(np.uint8)
        disagreements = int(np.count_nonzero((ones != 0) & (ones != copies)))

        rsc = RSCodec(nsym)

        def try_rs(bits) -> Optional[Tuple[bytes, int]]:
            try:
                decoded, _full, errata = rsc.decode(bits_to_bytes(bits.tolist()))
                return bytes(decoded), len(errata)
            except ReedSolomonError:
                return None

        used_source = "voted"
        rs_errors = 0
        message_bytes = None
        res = try_rs(majority_bits)
        if res is not None:
            message_bytes, rs_errors = res
        else:
            for bits in copy_bit_arrays:
                res = try_rs(bits)
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
            "bit_disagreements": disagreements,
            "rs_errors_corrected": rs_errors,
            "recovery_source": used_source,
        }
        return LayerResult(message=message, layer_key=self.name_key, info=info)


__all__ = ["LsbLayer", "header_repeats", "HEADER_ENC_BITS"]
