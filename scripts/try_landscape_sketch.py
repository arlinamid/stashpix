#!/usr/bin/env python3
"""Manual test: embed landscape_sky, extract from a stylized/sketch query image.

Usage:
  set PYTHONPATH=src
  python scripts/try_landscape_sketch.py embed
  python scripts/try_landscape_sketch.py extract --query path/to/sketch.png

Outputs go to packaging/out/sketch_try/ (registry + stego PNG).
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))

from PIL import Image

from stashpix.config import EmbedConfig, ExtractConfig
from stashpix.engine import StegoEngine
from stashpix.registry import Registry

ASSETS = os.path.join(ROOT, "tests", "assets", "landscape_sky.png")
OUT = os.path.join(ROOT, "packaging", "out", "sketch_try")
MSG = "Landscape sketch test message"
KEY = "sketch-try-key"


def _setup() -> StegoEngine:
    os.makedirs(OUT, exist_ok=True)
    reg = os.path.join(OUT, "registry.json")
    os.environ["STASHPIX_REGISTRY"] = reg
    return StegoEngine(registry=Registry(reg))


def cmd_embed(_args: argparse.Namespace) -> int:
    engine = _setup()
    stego_path = os.path.join(OUT, "landscape_stego.png")
    res = engine.embed_file(
        ASSETS,
        MSG,
        stego_path,
        EmbedConfig(key=KEY, enable_lsb=False, enable_robust=True),
    )
    print("Stego:", stego_path)
    print("Registry ID:", res.robust_id)
    print("Message embedded:", MSG)
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    engine = _setup()
    query = Image.open(args.query).convert("RGB")
    stego_path = os.path.join(OUT, "landscape_stego.png")
    if os.path.exists(stego_path):
        stego = Image.open(stego_path)
        if query.size != stego.size:
            print(f"Resizing query {query.size} -> {stego.size}")
            query = query.resize(stego.size, Image.LANCZOS)
    msg, info = engine.extract(query, ExtractConfig(key=KEY))
    print("Message:", msg)
    print("Layer:", info.get("layer_key"))
    print("Edge match:", info.get("edge_match"))
    print("Robust ID:", info.get("robust_id"))
    return 0 if msg == MSG else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("embed")
    p_ext = sub.add_parser("extract")
    p_ext.add_argument("--query", "-q", required=True, help="Stylized / sketch PNG to identify")
    args = parser.parse_args()
    if args.cmd == "embed":
        return cmd_embed(args)
    return cmd_extract(args)


if __name__ == "__main__":
    raise SystemExit(main())
