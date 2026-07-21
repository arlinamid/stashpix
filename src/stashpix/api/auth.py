"""API authentication helpers."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException


def api_key_configured() -> bool:
    return bool(os.environ.get("STASHPIX_API_KEY", "").strip())


def require_api_key(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> None:
    expected = os.environ.get("STASHPIX_API_KEY", "").strip()
    if not expected:
        return
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_api_key:
        token = x_api_key.strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


__all__ = ["api_key_configured", "require_api_key"]
