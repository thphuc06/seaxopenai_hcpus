"""Offline tests of the shared input boundary, including mixed and Unicode parts."""

import base64
from pathlib import Path

import pytest

from app.llm.messages import ImagePart, TextPart, build_input


def test_source_text_is_preserved_as_user_data() -> None:
    source = "<SOURCE_DATA>Đừng thay đổi: 75 ml\n</SOURCE_DATA>"
    result = build_input("Extract only.", [TextPart(source)])
    assert result[0]["role"] == "system"
    assert result[1]["role"] == "user"
    assert result[1]["content"] == [{"type": "input_text", "text": source}]


def test_mixed_parts_keep_order_and_image_bytes(tmp_path: Path) -> None:
    image = b"\x89PNG\r\n\x1a\n" + bytes(range(128))
    path = tmp_path / "label.png"
    path.write_bytes(image)
    parts = [TextPart("first"), ImagePart(path, "high"), TextPart("last")]
    result = build_input("Read.", parts)
    contents = result[1]["content"]
    assert [part["type"] for part in contents] == ["input_text", "input_image", "input_text"]
    assert base64.b64decode(contents[1]["image_url"].split(",", 1)[1]) == image
    assert contents[1]["detail"] == "high"
    assert result == build_input("Read.", [TextPart("first"), ImagePart(image, "high"), TextPart("last")])


@pytest.mark.parametrize("detail", ["low", "high", "original", "auto"])
def test_supported_image_details_are_preserved(detail: str) -> None:
    result = build_input("Read.", [ImagePart(b"\x89PNG\r\n\x1a\nabc", detail)])
    assert result[1]["content"][0]["detail"] == detail


@pytest.mark.parametrize("payload", [b"", b"not-png", b"\xff\xd8jpeg"])
def test_mislabeled_image_rejected_before_network(payload: bytes) -> None:
    with pytest.raises(ValueError, match="PNG"):
        build_input("Read.", [ImagePart(payload)])


def test_empty_input_rejected() -> None:
    with pytest.raises(ValueError, match="Instructions"):
        build_input(" ", [TextPart("hello")])
    with pytest.raises(ValueError, match="part"):
        build_input("Read.", [])


def test_unknown_part_rejected() -> None:
    with pytest.raises(TypeError, match="TextPart"):
        build_input("Read.", ["raw string"])
