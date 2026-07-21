"""Registry store tests."""

from stashpix.registry import Registry


def test_add_get_remove(tmp_path):
    reg = Registry(str(tmp_path / "r.json"))
    reg.add("abc", "secret", source_image="a.png", output_image="b.png")
    entry = reg.get("abc")
    assert entry is not None
    assert entry["message"] == "secret"
    assert reg.message_for("abc") == "secret"
    assert reg.remove("abc") is True
    assert reg.get("abc") is None
    assert reg.remove("abc") is False
