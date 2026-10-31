"""P2 retrieval interface; BM25 at S2, hybrid retrieval at S3."""
from dataclasses import dataclass
from pydantic import JsonValue


@dataclass
class SearchResult:
    hits: list[dict[str, JsonValue]]
    stages: dict[str, list[dict[str, JsonValue]]]


def index_source_version(sv_id: str) -> None:
    return None


def search(
    case_id: str, query: str, *, k: int = 8, mode: str = "auto",
    allowed_sv_ids: list[str] | None = None,
) -> SearchResult:
    return SearchResult([], {"bm25": []})
