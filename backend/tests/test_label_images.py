"""P4 label renderer checks with unrelated Vietnamese and long-token inputs."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from PIL import Image, ImageFilter, ImageStat
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.make_label_images import load_font, main, render_label, render_transcript, wrap_text


def label(path: Path, text: str, *, origin: str = "SYNTHETIC", kind: str = "PACKAGING_IMAGE") -> Path:
    path.write_text(json.dumps({
        "dataset_origin": origin, "kind": kind,
        "passages": [{"text": text}],
    }, ensure_ascii=False), encoding="utf-8")
    return path


def test_vietnamese_label_renders_without_changing_source(tmp_path: Path) -> None:
    path = label(tmp_path / "unrelated.v7.json", "NHÃN MINH HỌA\nSữa dưỡng thể — 85 ml.\nĐơn vị: Cơ sở Ánh Dương.")
    before = path.read_bytes()
    output = render_label(path)
    assert output == path.with_suffix(".png")
    assert path.read_bytes() == before
    with Image.open(output) as image:
        assert image.format == "PNG"
        assert image.size == (1280, 720)
        assert ImageStat.Stat(image.crop((56, 56, 1224, 664))).var[0] > 100
    first = output.read_bytes()
    render_label(path)
    assert output.read_bytes() == first


def test_long_token_and_diacritics_wrap_inside_width() -> None:
    font = load_font(30)
    text = "Dưỡng ẩm " + "X" * 180 + "\nThông tin cuối cùng."
    lines = wrap_text(text, font, 450)
    assert all(font.getlength(line) <= 450 for line in lines)
    assert "".join("".join(lines).split()) == "".join(text.split())


def test_too_long_transcript_fails_without_clipping() -> None:
    with pytest.raises(ValueError, match="does not fit"):
        render_transcript("Nhãn cần nhiều trang.\n" * 80)


def test_missing_font_reports_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="--font"):
        render_transcript("Nhãn có dấu tiếng Việt", tmp_path / "missing.ttf")


def test_blur_destroys_text_edges_and_preserves_empty_transcript(tmp_path: Path) -> None:
    readable = label(tmp_path / "readable.json", "NHÃN THỬ\nThể tích 85 ml.\nĐơn vị Ánh Dương.")
    original = render_label(readable)
    blurred = label(tmp_path / "blurred.json", "")
    before = blurred.read_bytes()
    destination = render_label(blurred, blur=True, blur_source=original)
    assert blurred.read_bytes() == before
    with Image.open(original) as clear, Image.open(destination) as result:
        assert result.size == (1280, 720)
        clear_edges = ImageStat.Stat(clear.convert("L").filter(ImageFilter.FIND_EDGES).crop((56, 56, 1224, 664))).mean[0]
        blur_edges = ImageStat.Stat(result.convert("L").filter(ImageFilter.FIND_EDGES).crop((56, 56, 1224, 664))).mean[0]
        assert blur_edges < clear_edges / 10


@pytest.mark.parametrize("text,blur,error", [
    ("", False, "nonempty transcript"),
    ("Readable", True, "empty transcript"),
    ("", True, "--blur-source"),
])
def test_invalid_blur_combinations_leave_no_output(tmp_path: Path, text: str, blur: bool, error: str) -> None:
    path = label(tmp_path / "input.json", text)
    with pytest.raises(ValueError, match=error):
        render_label(path, blur=blur)
    assert not path.with_suffix(".png").exists()


@pytest.mark.parametrize("origin,kind,error", [
    ("REAL", "PACKAGING_IMAGE", "only synthetic"),
    ("SYNTHETIC", "LISTING", "expected PACKAGING_IMAGE"),
])
def test_non_synthetic_or_non_image_rejected(tmp_path: Path, origin: str, kind: str, error: str) -> None:
    path = label(tmp_path / "input.json", "Example", origin=origin, kind=kind)
    with pytest.raises(ValueError, match=error):
        render_label(path)
    assert not path.with_suffix(".png").exists()


def test_cli_renders_and_returns_nonzero_for_invalid_source(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = label(tmp_path / "input.json", "Dữ liệu mới — 120 ml")
    assert main([str(path)]) == 0
    assert str(path.with_suffix(".png")) in capsys.readouterr().out
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        main([str(path)])
    assert error.value.code == 1
    assert "Label rendering failed" in capsys.readouterr().err
