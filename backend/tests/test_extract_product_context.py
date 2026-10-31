"""Gift sizes are not the main product; preserve genuine multiple-size claims."""
import json

import pytest

from app import db, store
from app.context import RunContext
from app.llm import client
from app.pipeline.extract import extract_source_version
from app.pipeline.normalize import volumes_in
from test_extract import context, source, raw_claim, provider_output


@pytest.mark.parametrize("text,expected", [
    ("Chai 125 ml. Tặng kèm lọ nhỏ 8 ml.", [125]),
    ("Chai 125 ml, tặng 1 chai du lịch 8ml", [125]),
    ("Chai 128 ml, tặng lọ 8 ml", [128]),
    ("Tặng lọ 8 ml khi mua chai 125 ml", [125]),
    ("Bottle 0.18 L with a free gift 12 ml", [180]),
    ("Free sample 12 ml with purchase of bottle 180 ml", [180]),
    ("Tặng kèm lọ 8 ml; Dung tích chai chính 125 ml", [125]),
    ("Tặng lọ 8 ml\nDung tích chai chính 125 ml", [125]),
    ("Chai 125 ml. Tặng kèm\nlọ du lịch 8 ml", [125]),
    ("Gift set: bottles 40 ml and 60 ml", [40, 60]),
    ("Bộ quà tặng: chai 40 ml và chai 60 ml", [40, 60]),
    ("Available sizes 40 ml and 60 ml", [40, 60]),
    ("Chai 125 ml. Dung tích 140 ml.", [125, 140]),
])
def test_fallback_distinguishes_gifts_without_hiding_multiple_sizes(context: RunContext, text: str, expected: list[int]) -> None:
    sv = source([text])
    result = extract_source_version(sv, context)
    assert sorted({c.normalized["value"] for c in result.claims if c.field_key == "volume"}) == expected
    assert len(volumes_in(text)) == 2  # Lexical normalization remains neutral for P1 scope.
    assert context.budget.model_calls == 0


@pytest.mark.parametrize("quote", ["8 ml", "tặng 1 chai 8 ml", "Chai 125 ml, tặng 1 chai 8 ml"])
def test_model_cannot_hide_gift_context_by_cropping_quote(context: RunContext, monkeypatch: pytest.MonkeyPatch, quote: str) -> None:
    text = "Chai 125 ml, tặng 1 chai 8 ml"
    sv = source([text])
    pid = store.passages(sv)[0]["id"]
    context.mode = "live"
    monkeypatch.setattr(client, "_call_api", lambda **kw: provider_output(sv, [
        raw_claim(pid, "125 ml", text), raw_claim(pid, "8 ml", quote)]))
    result = extract_source_version(sv, context)
    assert [c.normalized["value"] for c in result.claims] == [125]
    with db.transaction() as connection:
        trace = json.loads(connection.execute("SELECT detail FROM trace_steps WHERE step='extract' AND actor='code' ORDER BY seq DESC LIMIT 1").fetchone()[0])
        assert trace["rejected"]["PROMOTIONAL_CONTEXT"] == 1


def test_old_cache_cannot_reintroduce_gift_volume(context: RunContext) -> None:
    sv = source(["Tặng lọ 8 ml. Chai 125 ml."])
    with db.transaction() as connection:
        connection.execute("INSERT INTO extraction_cache VALUES(?,?,?,?,?,?)", (sv, "extract-v1", "FALLBACK:fallback-v2:image-v1", json.dumps({
            "claims": [], "ignored_instructions": False, "extractor": "FALLBACK", "cached": False}), 0, db.now_iso()))
    result = extract_source_version(sv, context)
    assert not result.cached and [c.normalized["value"] for c in result.claims] == [125]


@pytest.mark.parametrize("quote", ["8 ml", "Chai 128 ml, tặng lọ 8 ml"])
def test_gift_amount_cannot_match_suffix_of_main_amount(context: RunContext, monkeypatch: pytest.MonkeyPatch, quote: str) -> None:
    text = "Chai 128 ml, tặng lọ 8 ml"
    sv = source([text])
    pid = store.passages(sv)[0]["id"]
    context.mode = "live"
    monkeypatch.setattr(client, "_call_api", lambda **kw: provider_output(sv, [
        raw_claim(pid, "128 ml", text), raw_claim(pid, "8 ml", quote)]))
    assert [claim.normalized["value"] for claim in extract_source_version(sv, context).claims] == [128]


def test_whitespace_normalized_model_quote_preserves_original_clause_boundaries(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    text = "Tặng lọ 8 ml\nDung tích chai chính 125 ml"
    sv = source([text])
    pid = store.passages(sv)[0]["id"]
    context.mode = "live"
    quote = text.replace("\n", " ")
    monkeypatch.setattr(client, "_call_api", lambda **kw: provider_output(sv, [
        raw_claim(pid, "125 ml", quote), raw_claim(pid, "8 ml", quote)]))
    assert [claim.normalized["value"] for claim in extract_source_version(sv, context).claims] == [125]


def test_model_cropped_quote_cannot_hide_wrapped_offer(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    text = "Chai 125 ml. Tặng kèm\nlọ du lịch 8 ml"
    sv = source([text])
    pid = store.passages(sv)[0]["id"]
    context.mode = "live"
    monkeypatch.setattr(client, "_call_api", lambda **kw: provider_output(sv, [
        raw_claim(pid, "125 ml", "125 ml"), raw_claim(pid, "8 ml", "8 ml")]))
    assert [claim.normalized["value"] for claim in extract_source_version(sv, context).claims] == [125]


@pytest.mark.parametrize("text", ["Tặng kèm túi vải\nDung tích: 125 ml", "Free gift travel pouch\nCapacity: 125 ml"])
def test_unsized_gift_does_not_hide_new_product_header(context: RunContext, text: str) -> None:
    sv = source([text])
    assert [claim.normalized["value"] for claim in extract_source_version(sv, context).claims
            if claim.field_key == "volume"] == [125]
