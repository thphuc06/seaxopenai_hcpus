"""Immutable result history; append inside the publication writer transaction."""
from contextlib import closing
from hashlib import sha256
import sqlite3

from app import db
from app.models import ContractModel


IMMUTABLE_COLUMNS = (
    "field_key", "result_version", "case_revision", "verdict", "conflict_locus",
    "public_text", "citations_json", "explain_json", "seller_attributable",
    "review_state", "policy_version", "created_at",
)


class ChainLink(ContractModel):
    chain_seq: int
    prev_hash: str | None
    chain_hash: str


class ChainVerification(ContractModel):
    valid: bool
    rows: int
    head: str | None = None
    broken_at: str | None = None


def _digest(row: sqlite3.Row, sequence: int, previous: str | None) -> str:
    payload = {name: row[name] for name in IMMUTABLE_COLUMNS}
    payload.update(case_id=row["case_id"], result_id=row["id"],
                   chain_seq=sequence, prev_hash=previous)
    return sha256(db.dumps(payload).encode("utf-8")).hexdigest()


def _verify(rows: list[sqlite3.Row]) -> ChainVerification:
    previous = None
    for sequence, row in enumerate(rows, start=1):
        expected = _digest(row, sequence, previous)
        if (row["chain_seq"] != sequence or row["prev_hash"] != previous
                or row["chain_hash"] != expected):
            return ChainVerification(valid=False, rows=len(rows), broken_at=row["id"])
        previous = expected
    return ChainVerification(valid=True, rows=len(rows), head=previous)


def _rows(connection: sqlite3.Connection, case_id: str) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM field_results WHERE case_id=? ORDER BY "
        "chain_seq IS NULL,chain_seq,created_at,id", (case_id,),
    ).fetchall()


def append(connection: sqlite3.Connection, result_id: str) -> ChainLink:
    """Attach one new row atomically; never repair an existing chain or commit.

    Publication must call this immediately after INSERT in its BEGIN IMMEDIATE
    transaction. Reviews publish a new result row before calling this function.
    Confirming an unchanged version does not append another link.
    """
    if not connection.in_transaction:
        raise ValueError("Chain append requires a writer transaction")
    row = connection.execute("SELECT * FROM field_results WHERE id=?", (result_id,)).fetchone()
    if row is None:
        raise ValueError("Result not found")
    rows = _rows(connection, row["case_id"])
    if row["chain_hash"] is not None:
        if not _verify(rows).valid:
            raise ValueError("Existing result chain is invalid")
        return ChainLink(chain_seq=row["chain_seq"], prev_hash=row["prev_hash"], chain_hash=row["chain_hash"])
    if row["chain_seq"] is not None or row["prev_hash"] is not None:
        raise ValueError("Incomplete chain metadata")
    prefix = [item for item in rows if item["id"] != result_id]
    checked = _verify(prefix)
    if not checked.valid:
        raise ValueError("Prior results must have an intact chain")
    link = ChainLink(chain_seq=len(prefix)+1, prev_hash=checked.head,
                     chain_hash=_digest(row, len(prefix)+1, checked.head))
    connection.execute("UPDATE field_results SET chain_seq=?,prev_hash=?,chain_hash=? WHERE id=?",
                       (link.chain_seq, link.prev_hash, link.chain_hash, result_id))
    return link


def verify(case_id: str) -> ChainVerification:
    """Recompute stored links without changing any row, including missing links."""
    with closing(db.connect()) as connection:
        return verify_snapshot(connection, case_id)


def verify_snapshot(connection: sqlite3.Connection, case_id: str) -> ChainVerification:
    """Verify the chain inside a receipt/publication snapshot without opening a connection."""
    return _verify(_rows(connection, case_id))
