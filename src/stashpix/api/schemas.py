"""Pydantic response models for the REST API."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str


class ExtractResponse(BaseModel):
    ok: bool
    message: Optional[str] = None
    layer: Optional[str] = None
    info: Dict[str, Any] = {}
    detail: str = ""


class VerifyResponse(BaseModel):
    present: bool
    score: float
    threshold: float
    detail: str = ""


__all__ = ["HealthResponse", "ExtractResponse", "VerifyResponse"]
