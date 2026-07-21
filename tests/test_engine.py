"""End-to-end engine tests: full pipeline + graceful degradation."""

import io

from PIL import Image

from stegosuite.config import EmbedConfig, ExtractConfig, VerifyConfig


MSG = "Négyréteges titkos üzenet — áéíőű 4711"
VIS = "(c) Példa 2026"


def test_full_pipeline_lossless(engine, photo_path, tmp_path):
    out = tmp_path / "combo.png"
    res = engine.embed_file(photo_path, MSG, str(out),
                            EmbedConfig(key="pw", lsb_copies=3, visible_text=VIS))
    assert res.robust_id
    message, info = engine.extract_file(str(out), ExtractConfig(key="pw"))
    assert message == MSG
    assert info["layer_key"] == "lsb"


def test_graceful_degradation_jpeg(engine, photo_path, tmp_path):
    out = tmp_path / "combo.png"
    engine.embed_file(photo_path, MSG, str(out), EmbedConfig(key="pw", lsb_copies=3))
    jp = tmp_path / "combo.jpg"
    Image.open(out).convert("RGB").save(jp, "JPEG", quality=60)
    message, info = engine.extract_file(str(jp), ExtractConfig(key="pw"))
    assert message == MSG
    assert info["layer_key"] == "robust"


def test_visible_verify_via_engine(engine, photo_path, tmp_path):
    out = tmp_path / "combo.png"
    engine.embed_file(photo_path, MSG, str(out),
                      EmbedConfig(key="pw", visible_text=VIS))
    present, score, _ = engine.verify_visible_file(
        str(out), VerifyConfig(text=VIS, key="pw"))
    assert present is True
    present2, _, _ = engine.verify_visible_file(
        str(out), VerifyConfig(text="(c) Wrong 2026", key="pw"))
    assert present2 is False
