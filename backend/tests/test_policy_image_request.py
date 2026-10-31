"""Unreadable evidence requests tell the seller what replacement is needed."""
from dataclasses import replace
import pytest

from app.models import Readability
from app.pipeline import policy, publish
from p1_helpers import CoreDB, core_db


@pytest.mark.parametrize("field", ["volume", "skin_type"])
def test_unreadable_field_publishes_actionable_photo_request(core_db: CoreDB, field: str) -> None:
    source = core_db.source(text="Label photograph")
    unreadable = replace(source, field_key=field, readability=Readability.UNREADABLE,
                         quote="", normalized={})
    decision = policy.decide(field, [unreadable], {}, [], [])
    assert decision.verdict == "INSUFFICIENT"
    assert decision.citations == []
    assert decision.gap and decision.gap.missing_kind == "IMAGE"
    assert publish.gate(decision, core_db.run(), {"id": core_db.case_id, "revision": 0})
    request = core_db.rows("SELECT reason FROM evidence_requests WHERE field_key=?", (field,))[0]
    assert "clearer" in request["reason"].lower()
    assert "photo" in request["reason"].lower()
