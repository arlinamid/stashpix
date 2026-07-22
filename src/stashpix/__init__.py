"""stashpix — multi-layer steganography suite.

Public API::

    from stashpix import StegoEngine, EmbedConfig, ExtractConfig, VerifyConfig
    from stashpix import set_locale

    engine = StegoEngine()
    result = engine.embed_file("in.png", "secret", "out.png", EmbedConfig(key="pw"))
    message, info = engine.extract_file("out.png", ExtractConfig(key="pw"))
"""

from __future__ import annotations

from .config import (
    EmbedConfig,
    ExtractConfig,
    VerifyConfig,
)
from .exceptions import (
    StegoError,
    LossyFormatError,
    CapacityError,
    DecodeError,
    SelfVerifyError,
    RegistryError,
    DependencyError,
)
from .i18n import set_locale, get_locale, available_locales
from .paths import app_home, default_registry_path
from .engine import StegoEngine

__version__ = "1.4.0"

__all__ = [
    "__version__",
    "StegoEngine",
    "EmbedConfig",
    "ExtractConfig",
    "VerifyConfig",
    "StegoError",
    "LossyFormatError",
    "CapacityError",
    "DecodeError",
    "SelfVerifyError",
    "RegistryError",
    "DependencyError",
    "set_locale",
    "get_locale",
    "available_locales",
    "app_home",
    "default_registry_path",
]
