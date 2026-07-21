#!/usr/bin/env python3
"""Complete end-to-end stress test for the ``stashpix`` command-line interface.

This driver invokes the *real* CLI as a subprocess (``python -m stashpix.cli``)
against an isolated temporary registry, and runs a full battery of scenarios:

  * argparse / UX (help, missing args, exit codes)
  * lossless round-trips (LSB full recovery, unicode, message-file, auto-max copies)
  * key handling (correct vs. wrong key)
  * graceful degradation under lossy attacks (JPEG, resize) -> robust ID + registry
  * geometric recovery (sub-image paste) via ``extract-geo`` (SIFT)
  * partial occlusion tolerance
  * visible watermark verify (correct / wrong text / wrong key)
  * internationalization (--lang en / hu)
  * error handling (lossy input, missing file, empty extract)

Critical cases affect the exit code; "best-effort" robustness cases are reported
but never fail the run (they document real-world limits of the attacks).

Usage:
    python scripts/cli_stress_test.py [--keep] [--lang en|hu]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

try:
    import cv2
except ImportError:
    cv2 = None

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SAMPLE = ROOT / "tests" / "assets" / "sample.png"

MESSAGE = "Titkos uzenet — 2026 ✓ αβγ δ RÉGI-új #steg"
KEY = "s3cr3t-kulcs!"
VISIBLE = "(c) stashpix 2026"

# ----------------------------------------------------------------------------- infra

class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, bool, str]] = []  # name, ok, critical, detail

    def add(self, name: str, ok: bool, *, critical: bool = True, detail: str = "") -> bool:
        self.rows.append((name, ok, critical, detail))
        tag = "PASS" if ok else ("FAIL" if critical else "WARN")
        crit = "" if critical else "  (best-effort)"
        print(f"  [{tag}] {name}{crit}" + (f"  — {detail}" if detail else ""))
        return ok

    def summary(self) -> int:
        total = len(self.rows)
        passed = sum(1 for _, ok, _, _ in self.rows if ok)
        crit_fail = [n for n, ok, c, _ in self.rows if not ok and c]
        soft_fail = [n for n, ok, c, _ in self.rows if not ok and not c]
        print("\n" + "=" * 68)
        print(f"  RESULT: {passed}/{total} passed  |  "
              f"{len(crit_fail)} critical fail  |  {len(soft_fail)} best-effort miss")
        if crit_fail:
            print("  Critical failures:")
            for n in crit_fail:
                print(f"    - {n}")
        if soft_fail:
            print("  Best-effort misses (documented limits, non-fatal):")
            for n in soft_fail:
                print(f"    - {n}")
        print("=" * 68)
        return 1 if crit_fail else 0


class Runner:
    def __init__(self, workdir: Path) -> None:
        self.workdir = workdir
        self.env = os.environ.copy()
        self.env["PYTHONPATH"] = str(SRC) + os.pathsep + self.env.get("PYTHONPATH", "")
        self.env["PYTHONIOENCODING"] = "utf-8"
        self.env["STASHPIX_REGISTRY"] = str(workdir / "registry.json")

    def cli(self, *args: str, lang: str | None = None):
        cmd = [sys.executable, "-m", "stashpix.cli"]
        if lang:
            cmd += ["--lang", lang]
        cmd += [str(a) for a in args]
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", env=self.env)


# ----------------------------------------------------------------------------- attacks

def jpeg(src: Path, dst: Path, quality: int) -> Path:
    Image.open(src).convert("RGB").save(dst, "JPEG", quality=quality)
    return dst


def resize(src: Path, dst: Path, scale: float) -> Path:
    im = Image.open(src).convert("RGB")
    w, h = im.size
    im = im.resize((max(8, round(w * scale)), max(8, round(h * scale))), Image.LANCZOS)
    im.save(dst)
    return dst


def occlude(src: Path, dst: Path, frac: float) -> Path:
    im = Image.open(src).convert("RGB")
    w, h = im.size
    d = ImageDraw.Draw(im)
    bw, bh = int(w * frac), int(h * frac)
    x0, y0 = (w - bw) // 2, (h - bh) // 2
    d.rectangle([x0, y0, x0 + bw, y0 + bh], fill=(40, 40, 40))
    im.save(dst)
    return dst


def paste_into_scene(sub: Path, dst: Path, canvas=(760, 620), offset=(90, 70),
                     scale: float = 1.0) -> Path:
    s = Image.open(sub).convert("RGB")
    if scale != 1.0:
        s = s.resize((round(s.width * scale), round(s.height * scale)), Image.LANCZOS)
    rng = np.random.default_rng(7)
    bg = Image.fromarray(rng.integers(0, 256, (canvas[1], canvas[0], 3), dtype=np.uint8))
    bg.paste(s, offset)
    bg.save(dst)
    return dst


def reframe_on_solid(sub: Path, dst: Path, pad=(100, 120), bg=(46, 139, 87),
                     as_jpeg: bool = False) -> Path:
    """Letterbox/reframe onto a solid background, axis-aligned (no rotation)."""
    s = Image.open(sub).convert("RGB")
    canvas = Image.new("RGB", (s.width + 2 * pad[0], s.height + 2 * pad[1]), bg)
    canvas.paste(s, (pad[0], pad[1]))
    if as_jpeg:
        canvas.save(dst, "JPEG", quality=88)
    else:
        canvas.save(dst)
    return dst


def rotated_occluded_scene(sub: Path, dst: Path, angle=22.0, occ_frac=0.35,
                           bg=(46, 139, 87), scale=0.6) -> Path:
    """Rotate + occlude + solid bg + downscale + JPEG — a 'hard' sub-image."""
    s = np.asarray(Image.open(sub).convert("RGB"))
    h, w = s.shape[:2]
    canvas = np.full((h + 300, w + 300, 3), bg, np.uint8)
    canvas[150:150 + h, 150:150 + w] = s
    ch, cw = canvas.shape[:2]
    M = cv2.getRotationMatrix2D((cw / 2, ch / 2), angle, 1.0)
    rot = cv2.warpAffine(canvas, M, (cw, ch), borderValue=bg)
    rot[:, :int(cw * occ_frac)] = (120, 120, 120)
    small = cv2.resize(rot, (int(cw * scale), int(ch * scale)))
    Image.fromarray(small).save(dst, "JPEG", quality=85)
    return dst


# ----------------------------------------------------------------------------- fixtures

def make_photo(dst: Path, width: int = 512) -> Path:
    img = Image.open(SAMPLE).convert("RGB")
    w, h = img.size
    img.resize((width, max(1, round(width * h / w))), Image.LANCZOS).save(dst)
    return dst


def make_noise(dst: Path, size=(300, 300)) -> Path:
    rng = np.random.default_rng(0)
    arr = rng.integers(0, 256, (size[1], size[0], 3), dtype=np.uint8)
    Image.fromarray(arr, "RGB").save(dst)
    return dst


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


# ----------------------------------------------------------------------------- scenarios

def run_all(r: Runner, rep: Report, wd: Path) -> None:
    photo = make_photo(wd / "photo.png")
    noise = make_noise(wd / "noise.png")

    # ---- A. argparse / UX -------------------------------------------------
    print("\n[A] Argparse / UX")
    p = r.cli("--help")
    rep.add("--help exits 0 and lists subcommands",
            p.returncode == 0 and "embed" in p.stdout and "extract" in p.stdout,
            detail=f"rc={p.returncode}")
    p = r.cli()
    rep.add("no subcommand -> argparse error (rc=2)", p.returncode == 2,
            detail=f"rc={p.returncode}")
    p = r.cli("embed", "-i", str(photo))
    rep.add("embed without required args -> rc=2", p.returncode == 2,
            detail=f"rc={p.returncode}")

    # ---- B. lossless round-trips -----------------------------------------
    print("\n[B] Lossless round-trips (LSB full recovery)")
    stego_photo = wd / "stego_photo.png"
    p = r.cli("embed", "-i", photo, "-o", stego_photo, "-m", MESSAGE, "-k", KEY,
              "--visible-text", VISIBLE, lang="en")
    rep.add("embed (photo + key + visible) rc=0", p.returncode == 0 and stego_photo.exists(),
            detail=f"rc={p.returncode}")
    out = wd / "rec.txt"
    p = r.cli("extract", "-i", stego_photo, "-k", KEY, "--output-file", out,
              "--show-info", lang="en")
    rep.add("extract clean -> exact message via LSB",
            p.returncode == 0 and read(out) == MESSAGE and "layer_key: lsb" in p.stdout,
            detail=f"rc={p.returncode}")

    # high-redundancy copies on high-capacity noise + long message (within capacity)
    long_msg = ("STRESS-" * 40).strip()
    stego_n = wd / "stego_noise.png"
    p = r.cli("embed", "-i", noise, "-o", stego_n, "-m", long_msg, "-k", KEY,
              "--copies", "16", lang="en")
    rep.add("embed noise, copies=16 (high redundancy), long msg rc=0",
            p.returncode == 0 and stego_n.exists(), detail=f"rc={p.returncode}")
    out2 = wd / "rec_long.txt"
    p = r.cli("extract", "-i", stego_n, "-k", KEY, "--output-file", out2, "--show-info",
              lang="en")
    rep.add("extract long message from noise (16 copies) -> exact",
            p.returncode == 0 and read(out2) == long_msg, detail=f"rc={p.returncode}")

    # message-file + unicode
    msgfile = wd / "msg.txt"
    multiline = "Sor 1: αβγ\nSor 2: ✓✓✓\nSor 3: vége."
    msgfile.write_text(multiline, encoding="utf-8")
    stego_f = wd / "stego_file.png"
    p = r.cli("embed", "-i", photo, "-o", stego_f, "--message-file", msgfile, lang="en")
    out3 = wd / "rec_file.txt"
    r.cli("extract", "-i", stego_f, "--output-file", out3, lang="en")
    rep.add("message-file (multiline unicode) round-trip", read(out3) == multiline)

    # ---- C. key handling --------------------------------------------------
    print("\n[C] Key handling")
    out_wrong = wd / "rec_wrong.txt"
    p = r.cli("extract", "-i", stego_photo, "-k", "WRONG-KEY", "--output-file", out_wrong,
              lang="en")
    rep.add("wrong key does NOT recover the message",
            p.returncode == 2 and read(out_wrong) != MESSAGE,
            detail=f"rc={p.returncode}")

    # ---- D. lossy attacks -> robust ID + registry -------------------------
    print("\n[D] Lossy attacks -> graceful degradation (robust ID + registry)")
    j85 = jpeg(stego_photo, wd / "atk_jpeg85.jpg", 85)
    p = r.cli("extract", "-i", j85, "-k", KEY, "--show-info", lang="en")
    rep.add("JPEG q85: LSB dead, robust recovers message",
            p.returncode == 0 and MESSAGE in p.stdout and "layer_key: robust" in p.stdout,
            detail=f"rc={p.returncode}")

    j60 = jpeg(stego_photo, wd / "atk_jpeg60.jpg", 60)
    p = r.cli("extract", "-i", j60, "-k", KEY, "--show-info", lang="en")
    rep.add("JPEG q60: robust recovers message",
            p.returncode == 0 and MESSAGE in p.stdout,
            detail=f"rc={p.returncode}", critical=False)

    rs = resize(stego_photo, wd / "atk_resize.png", 0.75)
    p = r.cli("extract", "-i", rs, "-k", KEY, "--show-info", lang="en")
    rep.add("resize 75%: robust recovers message",
            p.returncode == 0 and MESSAGE in p.stdout,
            detail=f"rc={p.returncode}")

    # ---- E. geometric (sub-image paste) via extract-geo -------------------
    # Use the structured photo stashpix as the sub-image (SIFT needs real features;
    # pure random noise has no scale-stable keypoints).
    print("\n[E] Geometric recovery (SIFT sub-image)")
    scene = paste_into_scene(stego_photo, wd / "scene.png", canvas=(900, 820),
                             offset=(120, 90), scale=1.0)
    p = r.cli("extract-geo", "-i", scene, "-r", stego_photo, "-k", KEY, "--show-info",
              lang="en")
    geo_ok = p.returncode == 0 and MESSAGE in p.stdout
    rep.add("sub-image pasted into scene -> extract-geo recovers", geo_ok,
            detail=f"rc={p.returncode}", critical=False)

    scene2 = paste_into_scene(stego_photo, wd / "scene2.png", canvas=(900, 820),
                              offset=(150, 60), scale=0.9)
    p = r.cli("extract-geo", "-i", scene2, "-r", stego_photo, "-k", KEY, lang="en")
    rep.add("sub-image scaled 0.9 + pasted -> extract-geo recovers",
            p.returncode == 0 and MESSAGE in p.stdout,
            detail=f"rc={p.returncode}", critical=False)

    # reference-free blind recovery: reframed on a solid background (no rotation)
    frame_png = reframe_on_solid(stego_photo, wd / "reframe.png")
    p = r.cli("extract", "-i", frame_png, "-k", KEY, "--show-info", lang="en")
    rep.add("blind (no reference): reframed on solid bg -> recovers",
            p.returncode == 0 and MESSAGE in p.stdout and "blind_geo" in p.stdout,
            detail=f"rc={p.returncode}")
    frame_jpg = reframe_on_solid(stego_photo, wd / "reframe.jpg", as_jpeg=True)
    p = r.cli("extract", "-i", frame_jpg, "-k", KEY, lang="en")
    rep.add("blind (no reference): reframed on solid bg + JPEG -> recovers",
            p.returncode == 0 and MESSAGE in p.stdout,
            detail=f"rc={p.returncode}", critical=False)

    # auto registry image-match: rotated + occluded sub-image, NO reference given.
    # The engine matches it against stored references (SIFT) and self-recovers.
    if cv2 is not None:
        big = make_photo(wd / "big.png", width=960)
        big_stego = wd / "big_stego.png"
        r.cli("embed", "-i", big, "-o", big_stego, "-m", MESSAGE, "-k", KEY, lang="en")
        hard = rotated_occluded_scene(big_stego, wd / "hard.jpg", angle=18.0,
                                      occ_frac=0.30, scale=0.8)
        p = r.cli("extract", "-i", hard, "-k", KEY, "--show-info", lang="en")
        rep.add("auto-match (no reference): rotated+occluded sub-image -> recovers",
                p.returncode == 0 and MESSAGE in p.stdout and "auto_ref" in p.stdout,
                detail=f"rc={p.returncode}")

    # ---- F. partial occlusion --------------------------------------------
    print("\n[F] Partial occlusion")
    occ = occlude(stego_photo, wd / "atk_occ.png", 0.30)
    p = r.cli("extract", "-i", occ, "-k", KEY, lang="en")
    rep.add("30% center occlusion -> robust majority-vote recovers",
            p.returncode == 0 and MESSAGE in p.stdout,
            detail=f"rc={p.returncode}", critical=False)

    # ---- G. visible watermark verify -------------------------------------
    print("\n[G] Visible watermark verify")
    p = r.cli("verify-visible", "-i", stego_photo, "-t", VISIBLE, "-k", KEY, lang="en")
    rep.add("verify correct text+key -> present (rc=0)", p.returncode == 0,
            detail=f"rc={p.returncode}")
    p = r.cli("verify-visible", "-i", stego_photo, "-t", "WRONG TEXT", "-k", KEY, lang="en")
    rep.add("verify wrong text -> absent (rc=2)", p.returncode == 2,
            detail=f"rc={p.returncode}")
    p = r.cli("verify-visible", "-i", stego_photo, "-t", VISIBLE, "-k", "WRONG", lang="en")
    rep.add("verify wrong key -> absent (rc=2)", p.returncode == 2,
            detail=f"rc={p.returncode}", critical=False)
    vj = jpeg(stego_photo, wd / "vis_jpeg.jpg", 80)
    p = r.cli("verify-visible", "-i", vj, "-t", VISIBLE, "-k", KEY, lang="en")
    rep.add("verify after JPEG q80 -> still present", p.returncode == 0,
            detail=f"rc={p.returncode}", critical=False)

    # ---- H. i18n ----------------------------------------------------------
    print("\n[H] Internationalization")
    pen = r.cli("extract", "-i", stego_photo, "-k", KEY, lang="en")
    phu = r.cli("extract", "-i", stego_photo, "-k", KEY, lang="hu")
    rep.add("english vs hungarian output differ (localized)",
            pen.returncode == 0 and phu.returncode == 0 and pen.stdout != phu.stdout)

    # ---- I. error handling ------------------------------------------------
    print("\n[I] Error handling")
    badjpg = jpeg(photo, wd / "cover.jpg", 90)
    p = r.cli("embed", "-i", badjpg, "-o", wd / "x.png", "-m", "hi", lang="en")
    rep.add("lossy JPEG input for LSB -> error (rc=1)", p.returncode == 1,
            detail=f"rc={p.returncode}")
    p = r.cli("embed", "-i", wd / "does_not_exist.png", "-o", wd / "y.png",
              "-m", "hi", lang="en")
    rep.add("missing input file -> error (rc=1)", p.returncode == 1,
            detail=f"rc={p.returncode}")
    p = r.cli("extract", "-i", photo, "-k", KEY, lang="en")
    rep.add("extract on plain cover -> nothing found (rc=2)", p.returncode == 2,
            detail=f"rc={p.returncode}")
    # capacity overflow: many copies of a long message on a small cover
    p = r.cli("embed", "-i", noise, "-o", wd / "overflow.png",
              "-m", ("X" * 2000), "-k", KEY, "--copies", "200", lang="en")
    rep.add("capacity overflow (copies*msg > cover) -> error (rc=1)",
            p.returncode == 1, detail=f"rc={p.returncode}")
    # .jpg output is coerced to .png for lossless LSB storage
    jout = wd / "coerced.jpg"
    p = r.cli("embed", "-i", photo, "-o", jout, "-m", "coerce", lang="en")
    rep.add("lossy .jpg output coerced to .png",
            p.returncode == 0 and (wd / "coerced.png").exists() and not jout.exists(),
            detail=f"rc={p.returncode}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="keep the temp workdir")
    args = ap.parse_args()

    if not SAMPLE.exists():
        print(f"missing sample asset: {SAMPLE}", file=sys.stderr)
        return 1

    wd = Path(tempfile.mkdtemp(prefix="stego_stress_"))
    print("=" * 68)
    print("  stashpix — COMPLETE CLI STRESS TEST")
    print(f"  workdir : {wd}")
    print(f"  python  : {sys.executable}")
    print("=" * 68)

    rep = Report()
    r = Runner(wd)
    t0 = time.time()
    try:
        run_all(r, rep, wd)
    finally:
        code = rep.summary()
        print(f"  elapsed : {time.time() - t0:.1f}s")
        if args.keep:
            print(f"  kept    : {wd}")
        else:
            shutil.rmtree(wd, ignore_errors=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
