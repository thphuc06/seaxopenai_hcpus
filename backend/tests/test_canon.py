"""Learn only from persisted, located evidence and recheck each product's INCI."""
from dataclasses import replace
import json

import pytest

from app import db, store
from app.budget import Budget
from app.context import RunContext
from app.llm import client
from app.models import SourceKind, ScopeMatch
from app.pipeline import canon
from app.pipeline.extract import extract_source_version
from test_claims import observation
from test_extract import context, source, raw_claim, provider_output
from test_llm_client import response


def candidates(context: RunContext, monkeypatch: pytest.MonkeyPatch, *, surface="nghệ", inci="Curcuma Longa Root Extract"):
    sv = source(["Key ingredients: " + surface])
    pid = store.passages(sv)[0]["id"]
    context.mode = "live"
    monkeypatch.setattr(client, "_call_api", lambda **kw: provider_output(sv, [raw_claim(pid, surface, surface, field="key_ingredients")]))
    claim = extract_source_version(sv, context).claims[0]
    listing = observation(sv, field="key_ingredients", quote=surface, normalized=claim.normalized)
    snapshot = {"source_id": "reference", "product_id": "product", "kind": "PACKAGING_IMAGE", "version": 1,
                "passages": [{"locator": "label:ingredients", "text": "Ingredients: Water, " + inci}]}
    ref = store.add_source_version(snapshot, case_id="case", origin="SYNTHETIC").id
    context.mode = "fallback"
    raw = extract_source_version(ref, context).claims[0]
    reference = observation(ref, kind=SourceKind.PACKAGING_IMAGE, field="inci_list", quote=raw.quote, normalized=raw.normalized)
    context.mode = "record"
    return listing, reference


@pytest.mark.parametrize("surface,inci", [("nghệ", "Curcuma Longa Root Extract"), ("hoa cúc", "Chamomilla Recutita Flower Extract")])
def test_learned_mapping_persists_and_reuses_without_model(context: RunContext, monkeypatch: pytest.MonkeyPatch, surface: str, inci: str) -> None:
    listing, reference = candidates(context, monkeypatch, surface=surface, inci=inci)
    calls = []
    def provider(**request):
        calls.append(request)
        return response(text=json.dumps({"mappings": [{"field": "key_ingredients", "surface": surface,
            "passage_id": listing.passage_id, "inci_names": [inci], "skin_types": []}], "ignored_instructions_detected": False}))
    monkeypatch.setattr(client, "_call_api", provider)
    result = canon.learn_all(context, [listing, reference])
    assert result[0].mapped_by == "model" and result[0].normalized["by"] == "model"
    assert result[0].normalized["value"] == [inci.upper()]
    assert result[0].normalized["unknown"] == [] and result[1] is reference
    assert len(calls) == 1
    with db.transaction() as connection:
        saved = json.loads(connection.execute("SELECT value_json FROM vocab").fetchone()[0])
        assert saved["passage_id"] == listing.passage_id and saved["quote"] == surface
    context.mode = "fallback"
    assert canon.learn_all(context, [listing, reference]) == result
    assert len(calls) == 1
    # Same phrase without this product's supporting INCI cannot reuse a learned ingredient.
    assert canon.learn_all(context, [listing]) == [listing]


@pytest.mark.parametrize("bad", ["unknown_inci", "wrong_passage", "injection", "scope", "unpersisted"])
def test_unverified_mapping_is_not_stored(context: RunContext, monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    listing, reference = candidates(context, monkeypatch)
    if bad == "scope":
        reference = replace(reference, scope_match=ScopeMatch.UNKNOWN)
    if bad == "unpersisted":
        with db.transaction() as connection:
            connection.execute("DELETE FROM claims WHERE field_key='key_ingredients'")
    calls = []
    def provider(**request):
        calls.append(request)
        return response(text=json.dumps({"mappings": [{"field": "key_ingredients", "surface": "nghệ",
            "passage_id": "other" if bad == "wrong_passage" else listing.passage_id,
            "inci_names": ["Invented Root" if bad == "unknown_inci" else "Curcuma Longa Root Extract"],
            "skin_types": []}], "ignored_instructions_detected": bad == "injection"}))
    monkeypatch.setattr(client, "_call_api", provider)
    assert canon.learn_all(context, [listing, reference]) == [listing, reference]
    assert len(calls) == (0 if bad == "unpersisted" else 1)
    with db.transaction() as connection:
        assert connection.execute("SELECT COUNT(*) FROM vocab").fetchone()[0] == 0


def test_failed_canon_keeps_observations_and_budget(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    listing, reference = candidates(context, monkeypatch)
    context.budget = Budget(max_model_calls=0)
    monkeypatch.setattr(client, "_call_api", lambda **kw: pytest.fail("Budget must block provider"))
    assert canon.learn_all(context, [listing, reference]) == [listing, reference]
    assert context.budget.stop_reason == "MODEL_CALL_LIMIT"


def test_mixed_seed_and_learned_values_keep_separate_provenance(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.pipeline import policy
    listing, reference = candidates(context, monkeypatch, surface="Niacinamide, nghệ")
    context.product.update(case_id="case", tenant_id="tenant")
    before = policy.decide("key_ingredients", [listing, reference], context.product, [], [])
    assert before.verdict.value == "CONFLICTING"
    monkeypatch.setattr(client, "_call_api", lambda **kw: response(text=json.dumps({"mappings": [{
        "field": "key_ingredients", "surface": "nghệ", "passage_id": listing.passage_id,
        "inci_names": ["Curcuma Longa Root Extract"], "skin_types": []}], "ignored_instructions_detected": False})))
    learned = canon.learn_all(context, [listing, reference])
    assert learned[0] is listing
    assert learned[1].mapped_by == "model" and learned[1].normalized["value"] == ["CURCUMA LONGA ROOT EXTRACT"]
    assert "NIACINAMIDE" in learned[0].normalized["value"]
    after = policy.decide("key_ingredients", learned, context.product, [], [])
    assert after.verdict == before.verdict


def test_skin_phrase_is_learned_once_and_cached_in_a_new_run(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    surface = "peau sèche"
    sv = source([surface])
    pid = store.passages(sv)[0]["id"]
    context.mode = "live"
    monkeypatch.setattr(client, "_call_api", lambda **kw: provider_output(sv, [raw_claim(pid, surface, surface, field="skin_type")]))
    extract_source_version(sv, context)
    obs = observation(sv, field="skin_type", quote=surface)
    calls = []
    def provider(**request):
        calls.append(request)
        return response(text=json.dumps({"mappings": [{"field": "skin_type", "surface": surface,
            "passage_id": pid, "inci_names": [], "skin_types": ["DRY"]}], "ignored_instructions_detected": False}))
    monkeypatch.setattr(client, "_call_api", provider)
    learned = canon.learn_all(context, [obs])
    assert learned[0].normalized["value"] == ["DRY"] and learned[0].mapped_by == "model"
    assert canon.learn_all(context, [obs]) == learned and len(calls) == 1
    from app.trace import TraceWriter
    with db.transaction() as connection:
        connection.execute("INSERT INTO runs(id,case_id,started_at) VALUES('later-run','case',?)", (db.now_iso(),))
    later = replace(context, run_id="later-run", trace=TraceWriter("later-run"), budget=Budget())
    assert canon.learn_all(later, [obs]) == learned
    assert later.budget.model_calls == 0 and len(calls) == 1
