"""Shared pytest fixtures."""

import os

import numpy as np
import pytest
from PIL import Image

from stashpix.engine import StegoEngine
from stashpix.registry import Registry

ASSETS = os.path.join(os.path.dirname(__file__), "assets")


@pytest.fixture()
def tmp_registry(tmp_path, monkeypatch):
    path = tmp_path / "registry.json"
    monkeypatch.setenv("STASHPIX_REGISTRY", str(path))
    return Registry(str(path))


@pytest.fixture()
def engine(tmp_registry):
    return StegoEngine(registry=tmp_registry)


@pytest.fixture()
def photo_path(tmp_path):
    """A real photo downscaled to 512px width — realistic for DCT/visible tests."""
    img = Image.open(os.path.join(ASSETS, "sample.png")).convert("RGB")
    w, h = img.size
    img = img.resize((512, max(1, round(512 * h / w))), Image.LANCZOS)
    out = tmp_path / "photo.png"
    img.save(out)
    return str(out)


@pytest.fixture()
def large_photo_path(tmp_path):
    """Larger cover (~768px) for geometric / mild-attack tests."""
    img = Image.open(os.path.join(ASSETS, "sample.png")).convert("RGB")
    w, h = img.size
    target = 768
    img = img.resize((target, max(1, round(target * h / w))), Image.LANCZOS)
    out = tmp_path / "photo_large.png"
    img.save(out)
    return str(out)


@pytest.fixture()
def noise_path(tmp_path):
    """A small textured image — fast and high-capacity for LSB tests."""
    rng = np.random.default_rng(0)
    arr = rng.integers(0, 256, (240, 240, 3), dtype=np.uint8)
    out = tmp_path / "noise.png"
    Image.fromarray(arr, "RGB").save(out)
    return str(out)
