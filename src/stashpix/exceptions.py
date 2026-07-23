"""Exception hierarchy for stashpix.

Every exception stores an i18n message *key* plus format parameters, so its
``str()`` renders in whatever locale is active when it is displayed — not when
it is raised. This keeps error text out of the core logic and fully translatable.
"""

from __future__ import annotations

from .i18n import t


class StegoError(Exception):
    """Base class for all stashpix errors."""

    default_key = "error.generic"

    def __init__(self, key: str | None = None, **params):
        self.key = key or self.default_key
        self.params = params
        super().__init__(self.key)

    def __str__(self) -> str:
        return t(self.key, **self.params)


class LossyFormatError(StegoError):
    """Input/output uses a lossy image format that would destroy hidden data."""

    default_key = "error.lossy_format"


class CapacityError(StegoError):
    """The payload does not fit into the cover image."""

    default_key = "error.capacity"


class DecodeError(StegoError):
    """A hidden payload could not be decoded."""

    default_key = "error.decode_header"


class SelfVerifyError(StegoError):
    """Post-embed self-check failed."""

    default_key = "error.self_verify_mismatch"


class RegistryError(StegoError):
    """Registry lookup/storage problem."""

    default_key = "error.generic"


class DependencyError(StegoError):
    """An optional dependency required for a feature is missing."""

    default_key = "error.generic"


class AuthorshipError(StegoError):
    """Authorship identity / signature operation failed."""

    default_key = "error.authorship"


__all__ = [
    "StegoError",
    "LossyFormatError",
    "CapacityError",
    "DecodeError",
    "SelfVerifyError",
    "RegistryError",
    "DependencyError",
    "AuthorshipError",
]
