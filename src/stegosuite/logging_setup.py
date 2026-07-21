"""Central logging configuration.

Library code uses ``logging.getLogger("stegosuite...")`` and never prints
directly; presentation layers decide how to surface messages. Call
:func:`configure` once (CLI/GUI/API entry points) to attach a handler.
"""

from __future__ import annotations

import logging

_LOGGER_NAME = "stegosuite"


def get_logger(name: str | None = None) -> logging.Logger:
    if name:
        return logging.getLogger(f"{_LOGGER_NAME}.{name}")
    return logging.getLogger(_LOGGER_NAME)


def configure(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


__all__ = ["get_logger", "configure"]
