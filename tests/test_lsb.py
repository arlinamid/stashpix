"""LSB layer tests."""

import pytest
from PIL import Image

from stashpix.layers.lsb import LsbLayer
from stashpix.config import EmbedConfig, ExtractConfig
from stashpix.exceptions import DecodeError


def test_lsb_roundtrip(noise_path):
    layer = LsbLayer()
    img = Image.open(noise_path).convert("RGB")
    msg = "Titkos üzenet — LSB réteg #42"
    outcome = layer.embed(img, msg, EmbedConfig(key="pw", lsb_copies=3))
    result = layer.extract(outcome.image, ExtractConfig(key="pw"))
    assert result is not None
    assert result.message == msg


def test_lsb_wrong_key_fails(noise_path):
    layer = LsbLayer()
    img = Image.open(noise_path).convert("RGB")
    outcome = layer.embed(img, "secret", EmbedConfig(key="right", lsb_copies=3))
    with pytest.raises(DecodeError):
        layer.extract(outcome.image, ExtractConfig(key="wrong"))
