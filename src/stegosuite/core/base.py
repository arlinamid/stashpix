"""Abstract layer interface and result types shared by all steganography layers.

Each concrete layer (LSB, robust watermark, visible watermark) implements the
same small contract, so the engine can compose them into a pipeline without
knowing their internals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from PIL import Image


@dataclass
class EmbedOutcome:
    """Result of embedding one layer into an image."""

    image: Image.Image
    info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LayerResult:
    """Result of extracting from one layer."""

    message: Optional[str]
    layer_key: str
    info: Dict[str, Any] = field(default_factory=dict)


class Layer(ABC):
    """Common contract for a steganography layer.

    A layer transforms a cover image on embed and attempts to recover a payload
    on extract. Layers operate on in-memory :class:`PIL.Image.Image` objects so
    the engine can chain them without temporary files.
    """

    #: i18n key for the human-readable layer name.
    name_key: str = "layer.none"

    @abstractmethod
    def embed(self, image: Image.Image, message: str, config) -> EmbedOutcome:
        """Embed ``message`` into ``image``; return the modified image + info."""

    @abstractmethod
    def extract(self, image: Image.Image, config) -> Optional[LayerResult]:
        """Try to recover a message from ``image``; return ``None`` on failure."""


__all__ = ["Layer", "EmbedOutcome", "LayerResult"]
