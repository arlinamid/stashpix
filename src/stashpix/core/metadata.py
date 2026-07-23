"""Image metadata: preserve the source's, and write authorship fields.

Two separate jobs, and one honest caveat.

1. **Preserve.** ``Image.save`` drops EXIF/ICC unless you hand them back, so the
   old pipeline silently stripped the photographer's metadata on every embed.
   We now carry the source EXIF and ICC profile forward.

2. **Annotate.** We write standard authorship fields — Artist, Copyright,
   ImageDescription, Software, DateTime — plus stashpix specifics (the watermark
   UUID and the signer fingerprint) into both EXIF and PNG text chunks, so they
   are visible to ordinary tools (Explorer, exiftool, Lightroom).

The caveat, stated loudly because it matters: **metadata is not proof.** Anyone
can edit or strip EXIF in seconds. It is a discoverability and courtesy layer,
like the visible watermark — a convenient label, not evidence. The actual proof
of authorship is the Ed25519 signature over the watermark UUID (see
``core.authorship``), which is bound to the pixels via the robust watermark and
cannot be forged without the owner's key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from PIL import Image
from PIL.PngImagePlugin import PngInfo

# EXIF tag ids (baseline TIFF/EXIF).
_EXIF_IMAGE_DESCRIPTION = 0x010E
_EXIF_SOFTWARE = 0x0131
_EXIF_DATETIME = 0x0132
_EXIF_ARTIST = 0x013B
_EXIF_COPYRIGHT = 0x8298

SOFTWARE_TAG = "stashpix"


@dataclass
class ImageMetadata:
    """Authorship fields to stamp into the output image."""

    author: str = ""
    copyright_notice: str = ""
    description: str = ""
    datetime: str = ""          # "YYYY:MM:DD HH:MM:SS" EXIF form
    software: str = SOFTWARE_TAG
    watermark_id: str = ""
    signed_by: str = ""

    def is_empty(self) -> bool:
        return not any((self.author, self.copyright_notice, self.description,
                        self.watermark_id, self.signed_by))


def _exif_datetime(value: str) -> str:
    return value or ""


def build_exif(meta: ImageMetadata, *, source: Optional[Image.Image] = None) -> bytes:
    """EXIF block: source EXIF carried forward, our fields layered on top."""
    exif = source.getexif() if source is not None else Image.Exif()
    if meta.description:
        exif[_EXIF_IMAGE_DESCRIPTION] = meta.description
    if meta.author:
        exif[_EXIF_ARTIST] = meta.author
    if meta.copyright_notice:
        exif[_EXIF_COPYRIGHT] = meta.copyright_notice
    if meta.datetime:
        exif[_EXIF_DATETIME] = _exif_datetime(meta.datetime)
    exif[_EXIF_SOFTWARE] = meta.software or SOFTWARE_TAG
    return exif.tobytes()


def build_png_text(meta: ImageMetadata, *, source: Optional[Image.Image] = None) -> PngInfo:
    """PNG tEXt chunks — broadly read, and where our custom keys live.

    Custom keys are namespaced under ``stashpix:`` so they don't collide with
    standard ones and are obviously ours to any inspector.
    """
    info = PngInfo()
    # Carry forward any text the source PNG had.
    if source is not None:
        for key, value in (getattr(source, "text", {}) or {}).items():
            if isinstance(value, str):
                info.add_text(key, value)
    if meta.author:
        info.add_text("Author", meta.author)
    if meta.copyright_notice:
        info.add_text("Copyright", meta.copyright_notice)
    if meta.description:
        info.add_text("Description", meta.description)
    info.add_text("Software", meta.software or SOFTWARE_TAG)
    if meta.datetime:
        info.add_text("Creation Time", meta.datetime)
    if meta.watermark_id:
        info.add_text("stashpix:watermark_id", meta.watermark_id)
    if meta.signed_by:
        info.add_text("stashpix:signed_by", meta.signed_by)
    xmp = build_xmp(meta)
    if xmp:
        # Windows Explorer reads "Authors"/"Copyright" from XMP (dc:creator /
        # dc:rights), NOT from EXIF Artist/Copyright, so an EXIF-only PNG shows
        # those fields blank. The XMP packet is what makes them appear.
        info.add_itxt("XML:com.adobe.xmp", xmp, zip=False)
    return info


def build_xmp(meta: ImageMetadata) -> str:
    """Minimal XMP packet (dc:creator / dc:rights / xmp:CreatorTool).

    Windows' property system and most editors surface author/copyright from XMP
    across formats — including PNG, where EXIF Artist/Copyright is not read for
    the Explorer "Authors"/"Copyright" fields.
    """
    from xml.sax.saxutils import escape
    props = []
    if meta.author:
        props.append(
            f"<dc:creator><rdf:Seq><rdf:li>{escape(meta.author)}"
            f"</rdf:li></rdf:Seq></dc:creator>")
    if meta.copyright_notice:
        props.append(
            f'<dc:rights><rdf:Alt><rdf:li xml:lang="x-default">'
            f"{escape(meta.copyright_notice)}</rdf:li></rdf:Alt></dc:rights>")
    props.append(f"<xmp:CreatorTool>{escape(meta.software or SOFTWARE_TAG)}"
                 f"</xmp:CreatorTool>")
    if meta.description:
        props.append(
            f'<dc:description><rdf:Alt><rdf:li xml:lang="x-default">'
            f"{escape(meta.description)}</rdf:li></rdf:Alt></dc:description>")
    if not (meta.author or meta.copyright_notice or meta.description):
        return ""
    body = "".join(props)
    return (
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description rdf:about="" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:xmp="http://ns.adobe.com/xap/1.0/">'
        f"{body}"
        "</rdf:Description></rdf:RDF></x:xmpmeta>"
        '<?xpacket end="w"?>'
    )


def save_kwargs(meta: Optional[ImageMetadata], *, fmt: str,
                source: Optional[Image.Image] = None) -> Dict[str, Any]:
    """Assemble ``Image.save`` kwargs that preserve source + apply ``meta``.

    Works whether or not ``meta`` is given: with no meta we still forward the
    source's EXIF/ICC so nothing is silently dropped.
    """
    kwargs: Dict[str, Any] = {}
    icc = source.info.get("icc_profile") if source is not None else None
    if icc:
        kwargs["icc_profile"] = icc

    fmt = (fmt or "").upper()
    effective = meta or ImageMetadata()
    if fmt == "PNG":
        kwargs["pnginfo"] = build_png_text(effective, source=source)
        exif = build_exif(effective, source=source)
        if exif:
            kwargs["exif"] = exif
    elif fmt in ("TIFF", "JPEG", "JPG"):
        exif = build_exif(effective, source=source)
        if exif:
            kwargs["exif"] = exif
        xmp = build_xmp(effective)
        if xmp:
            kwargs["xmp"] = xmp.encode("utf-8")
    return kwargs


def read_metadata(img: Image.Image) -> Dict[str, Any]:
    """Best-effort read of authorship fields from EXIF + PNG text (for display).

    EXIF Artist/Copyright are ASCII-only tags, so a non-ASCII value (e.g. the ©
    sign or accented names) is mangled there. The PNG text chunk (UTF-8) keeps
    the true value, so it takes precedence for the text fields; EXIF fills gaps
    for formats without PNG text.
    """
    out: Dict[str, Any] = {}
    try:
        exif = img.getexif()
    except Exception:
        exif = {}
    mapping = {
        _EXIF_ARTIST: "author",
        _EXIF_COPYRIGHT: "copyright_notice",
        _EXIF_IMAGE_DESCRIPTION: "description",
        _EXIF_SOFTWARE: "software",
        _EXIF_DATETIME: "datetime",
    }
    for tag, name in mapping.items():
        if tag in exif and exif[tag]:
            out[name] = exif[tag]
    # PNG text overrides EXIF for the text fields (unicode-safe), and carries our
    # namespaced custom keys.
    for key, value in (getattr(img, "text", {}) or {}).items():
        if key.startswith("stashpix:"):
            out[key.split(":", 1)[1]] = value
        elif key in ("Author", "Copyright", "Description"):
            out[name_key(key)] = value
    return out


def name_key(png_key: str) -> str:
    return {"Author": "author", "Copyright": "copyright_notice",
            "Description": "description"}.get(png_key, png_key)


__all__ = [
    "ImageMetadata",
    "SOFTWARE_TAG",
    "build_exif",
    "build_png_text",
    "build_xmp",
    "save_kwargs",
    "read_metadata",
]
