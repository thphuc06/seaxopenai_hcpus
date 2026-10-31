"""Real publication with the explicit transaction hook delegated to P1 main."""
from contextlib import closing

import pytest

from app import chain, db
from app.pipeline import policy, publish
from p1_helpers import CoreDB, core_db

pytestmark = pytest.mark.phase(3)


def publish_link(harness: CoreDB, text: str = "Volume: 83 ml.", source: str = "chain-source") -> str:
    decision = policy.decide("volume", [harness.source(source_id=source, text=text)], {}, [], [])
    assert publish.gate(decision, harness.run(), {"id": harness.case_id})
    result_id = str(harness.rows("SELECT id FROM field_results WHERE superseded_by IS NULL")[0]["id"])
    with db.transaction() as connection:
        chain.append(connection, result_id)
    return result_id


def test_empty_and_idempotent_append(core_db: CoreDB) -> None:
    assert chain.verify(core_db.case_id).model_dump() == dict(valid=True, rows=0, head=None, broken_at=None)
    identity = publish_link(core_db)
    before = core_db.dump()
    with db.transaction() as connection:
        first = chain.append(connection, identity)
        assert chain.append(connection, identity) == first
    checked = chain.verify(core_db.case_id)
    assert checked.valid and checked.rows == 1 and checked.head == first.chain_hash
    assert first.chain_seq == 1 and first.prev_hash is None
    assert before == core_db.dump()


@pytest.mark.parametrize("column,value", [
    ("field_key", "skin_type"), ("result_version", 5), ("case_revision", 7),
    ("verdict", "UNCERTAIN"), ("conflict_locus", "WITHIN_SOURCE"),
    ("public_text", "Changed statement"), ("citations_json", "[]"),
    ("explain_json", "[]"), ("seller_attributable", 1),
    ("review_state", "REVIEWED"), ("policy_version", "changed"),
    ("created_at", "2026-11-01"), ("prev_hash", "broken"),
    ("chain_hash", "broken"), ("chain_seq", 9),
])
def test_tampering_is_detected_without_repair(core_db: CoreDB, column: str, value: str | int) -> None:
    identity = publish_link(core_db)
    with db.transaction() as connection:
        connection.execute(f"UPDATE field_results SET {column}=? WHERE id=?", (value, identity))
    before = core_db.dump()
    checked = chain.verify(core_db.case_id)
    assert not checked.valid and checked.broken_at == identity and checked.head is None
    assert core_db.dump() == before
    with db.transaction() as connection, pytest.raises(ValueError):
        chain.append(connection, identity)


def test_lifecycle_and_review_append_history(core_db: CoreDB) -> None:
    identity = publish_link(core_db)
    original_hash = chain.verify(core_db.case_id).head
    # Same decision reconfirms its version and leaves the chain untouched.
    publish_link(core_db)
    assert chain.verify(core_db.case_id).rows == 1
    assert chain.verify(core_db.case_id).head == original_hash
    with db.transaction() as connection:
        connection.execute("UPDATE field_results SET freshness='STALE',stale_reason='source event',stale_at=?,reviewed_by='actor' WHERE id=?", (db.now_iso(), identity))
    assert chain.verify(core_db.case_id).valid
    publish.review(core_db.case_id, identity, 0, "APPROVE", "Checked passage", None, "reviewer")
    current = str(core_db.rows("SELECT id FROM field_results WHERE superseded_by IS NULL")[0]["id"])
    assert current != identity
    # Deliberately remove the new link: this missing-metadata test must also work
    # after the main thread wires automatic publication chaining.
    with db.transaction() as connection:
        connection.execute("UPDATE field_results SET chain_seq=NULL,prev_hash=NULL,chain_hash=NULL WHERE id=?", (current,))
    assert not chain.verify(core_db.case_id).valid
    with db.transaction() as connection:
        linked = chain.append(connection, current)
    assert linked.chain_seq == 2 and linked.prev_hash == original_hash
    checked = chain.verify(core_db.case_id)
    assert checked.valid and checked.rows == 2 and checked.head == linked.chain_hash
    assert core_db.rows("SELECT chain_hash FROM field_results WHERE id=?", (identity,))[0]["chain_hash"] == original_hash


def test_append_rollback_and_missing_prior_link(core_db: CoreDB) -> None:
    decision = policy.decide("volume", [core_db.source()], {}, [], [])
    assert publish.gate(decision, core_db.run(), {"id": core_db.case_id})
    identity = str(core_db.rows("SELECT id FROM field_results")[0]["id"])
    # Establish the same unlinked setup with or without the publication hook.
    with db.transaction() as connection:
        connection.execute("UPDATE field_results SET chain_seq=NULL,prev_hash=NULL,chain_hash=NULL WHERE id=?", (identity,))
    with pytest.raises(RuntimeError), db.transaction() as connection:
        chain.append(connection, identity)
        raise RuntimeError("Caller rolls back")
    assert not chain.verify(core_db.case_id).valid
    with closing(db.connect()) as connection, pytest.raises(ValueError, match="writer transaction"):
        chain.append(connection, identity)
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="not found"):
            chain.append(connection, "absent")
        connection.execute("INSERT INTO field_results(id,case_id,field_key) VALUES('unchained',?,'skin_type')", (core_db.case_id,))
        with pytest.raises(ValueError, match="Prior results"):
            chain.append(connection, identity)


def test_cases_have_independent_heads_and_missing_middle_breaks(core_db: CoreDB) -> None:
    first = publish_link(core_db)
    second = publish_link(core_db, source="other-source")
    with db.transaction() as connection:
        connection.execute("INSERT INTO cases(id,product_id) VALUES('second-case',?)", (core_db.product_id,))
        connection.execute("INSERT INTO field_results(id,case_id,field_key) VALUES('other-result','second-case','volume')")
        other = chain.append(connection, "other-result")
    assert other.chain_seq == 1 and other.prev_hash is None
    assert chain.verify(core_db.case_id).rows == 2
    with db.transaction() as connection:
        connection.execute("UPDATE field_results SET chain_seq=NULL,chain_hash=NULL WHERE id=?", (first,))
    assert not chain.verify(core_db.case_id).valid
    assert chain.verify("second-case").valid
    assert second != first


def test_atomic_publication_hook_and_deleted_predecessor(core_db: CoreDB) -> None:
    first = publish_link(core_db)
    # Reproduce the main-thread integration point with actual publisher internals,
    # not a patched publisher: one writer transaction inserts and chains the row.
    decision = policy.decide("volume", [core_db.source(source_id="new-label")], {}, [], [])
    run = core_db.run()
    with db.transaction() as connection:
        second, unchanged = publish._record_result(connection, decision, str(run["id"]), core_db.case_id, db.now_iso())
        assert not unchanged
        chain.append(connection, second)
    assert chain.verify(core_db.case_id).rows == 2
    assert chain.verify(core_db.case_id).valid
    with db.transaction() as connection:
        # Remove referencing review tasks before deliberate tampering with history.
        connection.execute("DELETE FROM review_tasks WHERE result_id=?", (first,))
        connection.execute("DELETE FROM field_results WHERE id=?", (first,))
    checked = chain.verify(core_db.case_id)
    assert not checked.valid and checked.broken_at == second
