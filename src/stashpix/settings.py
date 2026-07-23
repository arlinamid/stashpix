"""Persistent user preferences (``settings.json`` under the app home).

Distinct from ``config.py``: that holds the parameters of a single embed/extract
call, this holds the durable defaults a user sets once (their author name and
copyright notice for image metadata, whether to sign, UI language). The GUI
Settings tab and the CLI read defaults from here.

Plain JSON on purpose — none of this is secret. Secrets (keys, identity) live
elsewhere and are wrapped/derived; see ``core.keys`` and ``core.authorship``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from .paths import app_home

_log = logging.getLogger(__name__)

SETTINGS_FILENAME = "settings.json"

DEFAULTS: Dict[str, Any] = {
    "author": "",              # written to image metadata (EXIF Artist / PNG Author)
    "copyright_notice": "",    # EXIF Copyright / PNG Copyright
    "sign": True,              # sign the registry claim with the authorship key
    "write_metadata": True,    # preserve source metadata + write authorship fields
    "language": "en",
}


def _settings_path():
    return app_home() / SETTINGS_FILENAME


def load() -> Dict[str, Any]:
    """Return stored settings merged over the defaults (defaults win for gaps)."""
    path = _settings_path()
    merged = dict(DEFAULTS)
    if path.is_file():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                merged.update({k: v for k, v in stored.items() if k in DEFAULTS})
        except (OSError, ValueError) as exc:
            _log.warning("Could not read settings (%s); using defaults", exc)
    return merged


def save(values: Dict[str, Any]) -> Dict[str, Any]:
    """Persist ``values`` (only known keys), returning the merged result."""
    merged = load()
    merged.update({k: v for k, v in values.items() if k in DEFAULTS})
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def get(key: str, default: Any = None) -> Any:
    return load().get(key, DEFAULTS.get(key, default))


def set(key: str, value: Any) -> Dict[str, Any]:  # noqa: A001 - deliberate api
    if key not in DEFAULTS:
        raise KeyError(f"unknown setting: {key}")
    return save({key: value})


__all__ = ["DEFAULTS", "SETTINGS_FILENAME", "load", "save", "get", "set"]
