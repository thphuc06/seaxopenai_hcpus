"""Retrieval metrics and source-derived expectation manifest, offline."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.retrieval_eval import QUESTIONS, metrics


def test_recall_counts_relevant_passages_and_mrr_counts_first_rank() -> None:
    recall, mrr = metrics([["x", "y"], ["z"]], [["x", "noise", "other", "y"], ["noise", "z"]])
    assert recall == 0.75
    assert mrr == 0.75


def test_metrics_include_no_hit_queries_in_denominator() -> None:
    assert metrics([["x"], ["y"]], [[], ["x", "y"]]) == (0.5, 0.25)


@pytest.mark.parametrize("expected,ranked", [([], []), ([["x"]], []), ([[]], [[]])])
def test_metrics_reject_empty_or_unaligned_expectations(expected: list[list[str]], ranked: list[list[str]]) -> None:
    with pytest.raises(ValueError):
        metrics(expected, ranked)


def test_expectations_have_bilingual_source_locators_before_execution() -> None:
    assert {q.language for q in QUESTIONS} == {"EN", "VI"}
    assert len(QUESTIONS) == 10
    assert all(q.source_id and q.locator and q.rationale for q in QUESTIONS)
