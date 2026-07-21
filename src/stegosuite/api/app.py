"""FastAPI application factory: REST endpoints + interactive web UI.

Endpoints
    GET  /                      -> interactive web dashboard (live state + tools)
    GET  /research              -> static research infographic
    GET  /api/health            -> service health
    GET  /api/stats             -> live service state (version, registry count...)
    GET  /api/registry          -> current registry entries
    GET  /api/i18n              -> web UI translations for a locale
    POST /api/embed             -> embed a message, returns the stego PNG
    POST /api/extract           -> extract a message (JSON)
    POST /api/verify-visible    -> verify a visible watermark (JSON)

Requires the optional ``api`` extra: fastapi, uvicorn, python-multipart.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..config import (
    EmbedConfig,
    ExtractConfig,
    VerifyConfig,
    DEFAULT_NSYM,
    DEFAULT_COPIES,
    DEFAULT_STRENGTH,
    DEFAULT_VISIBLE_OPACITY,
    DEFAULT_VISIBLE_THRESHOLD,
)
from ..engine import StegoEngine
from ..exceptions import StegoError
from ..i18n import set_locale, t, CATALOGS, available_locales
from .. import eula
from .schemas import HealthResponse, ExtractResponse, VerifyResponse

STATIC_DIR = Path(__file__).parent / "static"


def create_app():
    app = FastAPI(title="Stegosuite API", version=__version__)
    engine = StegoEngine()

    def _loc(lang):
        set_locale(lang)

    async def _read_image(file: UploadFile) -> Image.Image:
        if file is None:
            raise HTTPException(status_code=400, detail=t("api.err.no_file"))
        data = await file.read()
        return Image.open(io.BytesIO(data)).convert("RGB")

    @app.get("/", include_in_schema=False)
    def index():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"service": "stegosuite", "version": __version__}

    @app.get("/research", include_in_schema=False)
    def research():
        page = STATIC_DIR / "research.html"
        if page.exists():
            return FileResponse(str(page))
        raise HTTPException(status_code=404, detail="research page not found")

    @app.get("/api/health", response_model=HealthResponse)
    def health():
        return HealthResponse(status="ok", version=__version__)

    @app.get("/api/license")
    def license_info(lang: str = Query(None)):
        _loc(lang)
        return {
            "accepted": eula.is_accepted(),
            "eula_version": eula.EULA_VERSION,
            "status": eula.status_text(),
            "summary": eula.summary_text(),
        }

    @app.get("/api/stats")
    def stats():
        reg = engine.registry.all()
        return {
            "version": __version__,
            "registry_count": len(reg),
            "locales": available_locales(),
            "layers": [
                {"key": "lsb", "name": t("layer.lsb.name")},
                {"key": "robust", "name": t("layer.robust.name")},
                {"key": "visible", "name": t("layer.visible.name")},
            ],
            "geo_available": engine.geometry.available,
        }

    @app.get("/api/registry")
    def registry(limit: int = Query(100), lang: str = Query(None)):
        _loc(lang)
        reg = engine.registry.all()
        items = []
        for id_hex, entry in reg.items():
            msg = entry.get("message", "")
            items.append({
                "id": id_hex,
                "message": msg,
                "message_preview": (msg[:80] + "…") if len(msg) > 80 else msg,
                "created": entry.get("created", ""),
                "source_image": entry.get("source_image", ""),
                "output_image": entry.get("output_image", ""),
            })
        items.sort(key=lambda x: x["created"], reverse=True)
        return {"count": len(items), "items": items[:max(0, limit)]}

    @app.get("/api/i18n")
    def i18n(lang: str = Query(None)):
        loc = set_locale(lang)
        catalog = CATALOGS.get(loc, {})
        fallback = CATALOGS.get("en", {})
        web = {k: catalog.get(k, fallback.get(k, k))
               for k in fallback if k.startswith("web.")}
        return {"locale": loc, "strings": web}

    @app.post("/api/embed")
    async def embed(
        file: UploadFile = File(...),
        message: str = Form(...),
        key: str = Form(""),
        nsym: int = Form(DEFAULT_NSYM),
        copies: int = Form(DEFAULT_COPIES),
        strength: float = Form(DEFAULT_STRENGTH),
        visible_text: str = Form(""),
        visible_opacity: float = Form(DEFAULT_VISIBLE_OPACITY),
        lang: str = Query(None),
    ):
        _loc(lang)
        if not message:
            raise HTTPException(status_code=400, detail=t("api.err.no_message"))
        img = await _read_image(file)
        config = EmbedConfig(
            key=key or None, lsb_nsym=nsym, lsb_copies=copies,
            robust_strength=strength, visible_text=visible_text or None,
            visible_opacity=visible_opacity,
        )
        try:
            result_img, info = engine.embed(img, message, config,
                                            source_image=file.filename or "upload")
        except StegoError as e:
            raise HTTPException(status_code=400, detail=str(e))

        buf = io.BytesIO()
        result_img.save(buf, format="PNG")
        buf.seek(0)
        headers = {
            "X-Robust-Id": info.get("robust_id") or "",
            "Content-Disposition": "attachment; filename=stego.png",
        }
        return StreamingResponse(buf, media_type="image/png", headers=headers)

    @app.post("/api/extract", response_model=ExtractResponse)
    async def extract(
        file: UploadFile = File(...),
        key: str = Form(""),
        strength: float = Form(DEFAULT_STRENGTH),
        reference: UploadFile = File(None),
        lang: str = Query(None),
    ):
        _loc(lang)
        img = await _read_image(file)
        config = ExtractConfig(key=key or None, robust_strength=strength)
        if reference is not None and (reference.filename or ""):
            ref = await _read_image(reference)
            message, info = engine.extract_geo(img, ref, config)
        else:
            message, info = engine.extract(img, config)
        if message is None:
            return ExtractResponse(ok=False, info=_safe(info), detail=t("api.extract.none"))
        return ExtractResponse(ok=True, message=message, layer=info.get("layer"),
                               info=_safe(info), detail=t("api.extract.ok"))

    @app.post("/api/verify-visible", response_model=VerifyResponse)
    async def verify_visible(
        file: UploadFile = File(...),
        text: str = Form(...),
        key: str = Form(""),
        threshold: float = Form(DEFAULT_VISIBLE_THRESHOLD),
        lang: str = Query(None),
    ):
        _loc(lang)
        img = await _read_image(file)
        present, score, _info = engine.verify_visible(
            img, VerifyConfig(text=text, key=key or None, threshold=threshold))
        return VerifyResponse(present=present, score=round(score, 4),
                              threshold=threshold, detail=t("api.verify.ok"))

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app


def _safe(info: dict) -> dict:
    """Drop non-JSON-serializable values (e.g. nested tuples are fine, but keep it lean)."""
    out = {}
    for k, v in info.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, dict):
            out[k] = {kk: vv for kk, vv in v.items()
                      if isinstance(vv, (str, int, float, bool)) or vv is None}
    return out


__all__ = ["create_app"]
