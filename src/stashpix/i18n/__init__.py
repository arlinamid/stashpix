"""Lightweight internationalization (i18n) layer.

All user-facing strings live in message catalogs keyed by a stable message id.
The rest of the codebase never hardcodes user text; it calls :func:`t` with a
key and format parameters. Presentation layers (CLI, GUI, API) render strings in
the currently selected locale.

Supported locales: English (``en``) and Hungarian (``hu``).
"""

from __future__ import annotations

import os
import threading
from typing import Dict

from .catalog_en import CATALOG as _EN
from .catalog_hu import CATALOG as _HU

CATALOGS: Dict[str, Dict[str, str]] = {"en": _EN, "hu": _HU}
DEFAULT_LOCALE = "hu"
FALLBACK_LOCALE = "en"

_state = threading.local()


def available_locales() -> list[str]:
    return list(CATALOGS.keys())


def _initial_locale() -> str:
    env = os.environ.get("STASHPIX_LANG", "").strip().lower()
    if env in CATALOGS:
        return env
    return DEFAULT_LOCALE


def get_locale() -> str:
    return getattr(_state, "locale", None) or _initial_locale()


def set_locale(locale: str) -> str:
    """Set the active locale for the current thread. Falls back silently if the
    requested locale is unknown. Returns the effective locale."""
    locale = (locale or "").strip().lower()
    if locale not in CATALOGS:
        locale = _initial_locale()
    _state.locale = locale
    return locale


def t(key: str, /, **params) -> str:
    """Translate ``key`` into the active locale and format with ``params``.

    Resolution order: active locale → fallback locale → the raw key itself
    (so a missing translation is visible but never crashes)."""
    locale = get_locale()
    template = CATALOGS.get(locale, {}).get(key)
    if template is None:
        template = CATALOGS.get(FALLBACK_LOCALE, {}).get(key, key)
    try:
        return template.format(**params) if params else template
    except (KeyError, IndexError):
        return template


__all__ = ["t", "set_locale", "get_locale", "available_locales", "CATALOGS"]
