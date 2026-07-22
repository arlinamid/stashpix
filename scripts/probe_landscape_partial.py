"""Probe partial identification on tests/assets/landscape_sky.png."""

from __future__ import annotations

import os
import sys

from PIL import Image

from stashpix.config import EmbedConfig, ExtractConfig
from stashpix.core.perceptual import edge_hash_hex, hamming_hex, phash_hex
from stashpix.engine import StegoEngine
from stashpix.layers.geometry import GeometricSynchronizer
from stashpix.registry import Registry

ASSETS = os.path.join(os.path.dirname(__file__), "..", "tests", "assets")
COVER = os.path.join(ASSETS, "landscape_sky.png")
SKETCH = (
    r"C:\Users\arlin\.cursor\projects\d-tool-steganography\assets"
    r"\c__Users_arlin_AppData_Roaming_Cursor_User_workspaceStorage_67bb4351e2d0458d0c95e12164c13b6b"
    r"_images_imageedit_7_8204649905-a3cc3386-af17-46d5-9ea9-d92db5dc3036.png"
)
MSG = "Landscape sky partial ID test"
KEY = "landscape-key"
OUT = os.path.join(os.path.dirname(__file__), "..", "packaging", "out", "landscape_probe")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    reg_path = os.path.join(OUT, "registry.json")
    os.environ["STASHPIX_REGISTRY"] = reg_path
    engine = StegoEngine(registry=Registry(reg_path))
    GeometricSynchronizer()

    cover = Image.open(COVER).convert("RGB")
    w, h = cover.size
    target_w = 768
    if w > target_w:
        cover = cover.resize((target_w, max(1, round(h * target_w / w))), Image.LANCZOS)
        w, h = cover.size

    cover_path = os.path.join(OUT, "cover_768.png")
    cover.save(cover_path)
    stego_path = os.path.join(OUT, "landscape_stego.png")
    res = engine.embed_file(
        cover_path,
        MSG,
        stego_path,
        EmbedConfig(key=KEY, enable_lsb=False, enable_robust=True),
    )
    stego = Image.open(stego_path).convert("RGB")
    print(f"embed id={res.robust_id} size={stego.size}")

    def try_extract(label: str, img: Image.Image):
        path = os.path.join(OUT, f"q_{label}.png")
        img.save(path)
        msg, info = engine.extract(img, ExtractConfig(key=KEY, edge_match=True))
        auto = info.get("auto_ref") or {}
        return (
            msg,
            info.get("layer_key"),
            (info.get("edge_match") or {}).get("distance"),
            auto.get("matched"),
            auto.get("inliers"),
            info,
        )

    crops = {
        "full": (0, 0, w, h),
        "center50": (w // 4, h // 4, 3 * w // 4, 3 * h // 4),
        "center35": (int(w * 0.325), int(h * 0.325), int(w * 0.675), int(h * 0.675)),
        "center25": (int(w * 0.375), int(h * 0.375), int(w * 0.625), int(h * 0.625)),
        "left_peak": (0, 0, w // 2, int(h * 0.55)),
        "right_horizon": (w // 2, int(h * 0.35), w, int(h * 0.65)),
        "mountains_only": (0, int(h * 0.25), w, int(h * 0.75)),
        "sky_only": (0, 0, w, int(h * 0.35)),
        "clouds_only": (0, int(h * 0.45), w, h),
    }

    print("\n=== Extract without reference (registry auto) ===")
    for name, box in crops.items():
        q = stego.crop(box)
        msg, layer, dist, matched, inliers, _ = try_extract(name, q)
        ok = "OK" if msg == MSG else "FAIL"
        print(
            f"{ok:4} {name:14} {q.size[0]}x{q.size[1]:<4} "
            f"layer={str(layer):12} edge_dist={dist} auto={matched} inliers={inliers}"
        )

    print("\n=== Extract with stego reference (extract_geo) ===")
    for name in ("center35", "center25", "left_peak"):
        q = stego.crop(crops[name])
        msg, info = engine.extract_geo(q, stego, ExtractConfig(key=KEY))
        layer = info.get("layer_key")
        ok = "OK" if msg == MSG else "FAIL"
        geo = info.get("geo_tps") or info.get("geo") or {}
        reg = geo.get("registered")
        inl = geo.get("inliers")
        print(f"{ok:4} {name:14} layer={str(layer):12} geo_reg={reg} inliers={inl}")

    ref_path = engine.registry.reference_path(res.robust_id)
    ref_img = Image.open(ref_path).convert("RGB")
    print("\n=== Fingerprint distance vs registry ref ===")
    for name, box in crops.items():
        q = stego.crop(box)
        ep = hamming_hex(edge_hash_hex(ref_img), edge_hash_hex(q))
        pp = hamming_hex(phash_hex(ref_img), phash_hex(q))
        ranked = engine.registry.ranked_reference_ids(q, top_k=1)
        print(f"{name:14} edge={ep:2} phash_part={pp:2} ranked={ranked}")

    if os.path.exists(SKETCH):
        sketch = Image.open(SKETCH).convert("RGB")
        sketch = sketch.resize(stego.size, Image.LANCZOS)
        msg, layer, dist, matched, inliers, _ = try_extract("sketch_resized", sketch)
        ep = hamming_hex(edge_hash_hex(ref_img), edge_hash_hex(sketch))
        pp = hamming_hex(phash_hex(ref_img), phash_hex(sketch))
        resolved = engine.registry.resolve_fingerprint(sketch)
        print("\n=== User sketch (resized to stego) ===")
        print(f"extract msg={msg!r} layer={layer} edge_dist={dist}")
        print(f"hamming edge={ep} phash={pp} resolve={resolved}")

    from tests.geo_helpers import require_cv2

    try:
        require_cv2()
        print("\n=== Piece on green canvas (auto registry geo) ===")
        for frac, name in ((0.55, "center55"), (0.45, "center45"), (0.35, "center35")):
            cw, ch = int(w * frac), int(h * frac)
            piece = stego.crop(((w - cw) // 2, (h - ch) // 2, (w + cw) // 2, (h + ch) // 2))
            canvas = Image.new("RGB", (w, h), (0, 180, 0))
            canvas.paste(piece, ((w - cw) // 2, (h - ch) // 2))
            msg, layer, dist, matched, inliers, info = try_extract(f"{name}_on_green", canvas)
            mode = (info.get("auto_ref") or {}).get("mode")
            ok = "OK" if msg == MSG else "FAIL"
            print(
                f"{ok:4} {name+'_on_green':18} layer={str(layer):10} "
                f"matched={matched} inliers={inliers} mode={mode}"
            )

        piece = stego.crop((0, int(h * 0.25), w, int(h * 0.75)))
        canvas = Image.new("RGB", (w, h), (0, 180, 0))
        canvas.paste(piece, (0, int(h * 0.25)))
        msg, layer, dist, matched, inliers, info = try_extract("mountains_on_green", canvas)
        mode = (info.get("auto_ref") or {}).get("mode")
        ok = "OK" if msg == MSG else "FAIL"
        print(
            f"{ok:4} {'mountains_on_green':18} layer={str(layer):10} "
            f"matched={matched} inliers={inliers} mode={mode}"
        )

        print("\n=== Piece on green with extract_geo + stego ref ===")
        for frac, name in ((0.55, "center55"), (0.35, "center35")):
            cw, ch = int(w * frac), int(h * frac)
            piece = stego.crop(((w - cw) // 2, (h - ch) // 2, (w + cw) // 2, (h + ch) // 2))
            canvas = Image.new("RGB", (w, h), (0, 180, 0))
            canvas.paste(piece, ((w - cw) // 2, (h - ch) // 2))
            msg, info = engine.extract_geo(canvas, stego, ExtractConfig(key=KEY))
            geo = info.get("geo_tps") or info.get("geo") or {}
            ok = "OK" if msg == MSG else "FAIL"
            print(
                f"{ok:4} {name+'_on_green':18} layer={str(info.get('layer_key')):10} "
                f"reg={geo.get('registered')} inliers={geo.get('inliers')}"
            )
    except Exception as exc:
        print(f"\n(OpenCV piece tests skipped: {exc})")

    return 0



if __name__ == "__main__":
    sys.exit(main())
