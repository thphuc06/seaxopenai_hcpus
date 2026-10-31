"""Generic normalization variants; no product fixture special cases."""
import unicodedata

import pytest

from app.pipeline.normalize import company_key, normalize, parse_inci, skin_types_in, volumes_in


@pytest.mark.parametrize("text,value,unit", [("0.2 L", 200, "ml"), ("16 fl oz", 473.176, "ml"),
    ("0,35 kg", 350, "g"), ("  97 ML  ", 97, "ml"), ("2 fl. oz.", 59.147, "ml"), ("8g", 8, "g")])
def test_volume_units_and_variants(text: str, value: float, unit: str) -> None:
    result = volumes_in(text)
    assert len(result) == 1
    assert result[0]["value"] == pytest.approx(value)
    assert result[0]["unit"] == unit and result[0]["by"] == "code"


def test_multi_volume_kept_separate_and_mass_not_volume() -> None:
    assert len(volumes_in("20 ml / 30 ml / 40 g")) == 3
    assert normalize("volume", "20 ml and 30 ml") is None
    assert normalize("volume", "-2 ml") is None
    assert volumes_in("123milk") == []


@pytest.mark.parametrize("text,expected", [
    ("da thường đến da dầu", {"NORMAL", "COMBINATION", "OILY"}),
    ("normal-to-oily skin", {"NORMAL", "COMBINATION", "OILY"}),
    ("da thường, da dầu", {"NORMAL", "OILY"}), ("da khô và da nhạy cảm", {"DRY", "SENSITIVE"}),
    ("all skin types", {"ALL"}),
])
def test_skin_phrases_case_accents_and_spacing(text: str, expected: set[str]) -> None:
    without_marks = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").replace("đ", "d")
    for variant in (text, text.upper(), without_marks, text.replace(" ", "  "), unicodedata.normalize("NFD", text)):
        assert skin_types_in(variant) == expected


def test_unknown_skin_not_guessed_from_model() -> None:
    assert normalize("skin_type", "undocumented phrase", ["DRY"]) is None
    assert skin_types_in("skin dryness") == set()


def test_inci_retains_abbreviations_and_order() -> None:
    text = "Water, Alcohol Denat., Botanical Ext.; Botanical Extr.\nBotanical Fil., Glycerin"
    assert parse_inci(text) == ["Water", "Alcohol Denat.", "Botanical Ext.", "Botanical Extr.", "Botanical Fil.", "Glycerin"]
    result = normalize("inci_list", text)
    assert result["value"] == ["WATER", "ALCOHOL DENAT", "BOTANICAL EXT", "BOTANICAL EXTR", "BOTANICAL FIL", "GLYCERIN"]


@pytest.mark.parametrize("form", ["Công ty TNHH", "Cty TNHH", "Công ty CP", "Công ty Cổ phần", "TNHH MTV", "JSC", "Co., Ltd", "LLC"])
def test_company_legal_forms(form: str) -> None:
    assert company_key(f"{form}  Ánh  Dương") == company_key(f"ÁNH DƯƠNG {form}") == "ánh dương"
    assert company_key("Shellcraft") == "shellcraft"


def test_ingredient_provenance_and_unknown_names() -> None:
    assert normalize("key_ingredients", "Sodium Hyaluronate")["value"] == ["HYALURONIC_ACID"]
    assert normalize("key_ingredients", "Unlisted Botanical")["unknown"] == ["Unlisted Botanical"]
    assert normalize("inci_list", "Unlisted Botanical")["value"] == ["UNLISTED BOTANICAL"]
    assert normalize("key_ingredients", "zincate")["value"] == []
    assert normalize("notification_number", " ab - 123 / 26 ")["value"] == "AB123/26"
    assert normalize("volume", None) is None


def test_company_accents_are_identity_not_cosmetic() -> None:
    assert company_key("Công ty TNHH An") != company_key("Công ty TNHH Ấn")
    assert company_key(unicodedata.normalize("NFD", "Công ty TNHH Ấn")) == "ấn"


@pytest.mark.parametrize("text", ["Niacinamide, Panthenol", "Panthenol and niacinamide", "Niacinamide và Panthenol", "NIACINAMIDE + Panthenol", "Niacinamide+Panthenol", "Niacinamide&Panthenol", unicodedata.normalize("NFD", "Niacinamide và Panthenol")])
def test_mixed_unknown_ingredients_are_retained(text: str) -> None:
    result = normalize("key_ingredients", text)
    assert result["value"] == ["NIACINAMIDE"]
    assert result["unknown"] == ["Panthenol"]


@pytest.mark.parametrize("text", ["Not for dry skin", "Không dành cho da khô", "Contains no niacinamide", "Không chứa niacinamide"])
def test_negated_mentions_are_not_positive_values(text: str) -> None:
    assert not skin_types_in(text)
    assert normalize("key_ingredients", text) is None
