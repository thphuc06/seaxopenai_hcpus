"""Pure marketplace tallies; no extraction, persistence or passport publication."""
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from pydantic import JsonValue

from app import db
from app.pipeline.compare import compatible
from app.pipeline.scope import copy_shingles, shingle_jaccard


@dataclass(frozen=True)
class SellerListing:
    seller_id: str
    text: str
    values: Mapping[str, JsonValue]


@dataclass(frozen=True)
class CopyCluster:
    cluster_id: str
    seller_ids: tuple[str, ...]


@dataclass(frozen=True)
class ValueVotes:
    value: JsonValue
    cluster_ids: tuple[str, ...]


@dataclass(frozen=True)
class FieldConsensus:
    field_key: str
    independent_clusters: int
    values: tuple[ValueVotes, ...]
    majority: JsonValue
    outlier_seller_ids: tuple[str, ...]
    abstaining_cluster_ids: tuple[str, ...]


@dataclass(frozen=True)
class MarketplaceConsensus:
    clusters: tuple[CopyCluster, ...]
    fields: tuple[FieldConsensus, ...]


def cluster_copies(listings: Sequence[SellerListing]) -> tuple[CopyCluster, ...]:
    """Connected components at Jaccard >=0.8; empty/short text supplies no copy signal."""
    ordered = sorted(listings, key=lambda item: item.seller_id)
    ids = [item.seller_id for item in ordered]
    tokens = {item.seller_id: copy_shingles(item.text) for item in ordered}
    links = ((left, right) for index, left in enumerate(ids) for right in ids[index + 1:]
             if shingle_jaccard(tokens[left], tokens[right]) >= 0.8)
    return cluster_links(ids, links)


def cluster_links(identities: Sequence[str], links: Iterable[tuple[str, str]]) -> tuple[CopyCluster, ...]:
    """Shared deterministic union-find for code-validated copy links."""
    ids = sorted(identities)
    if any(not identity.strip() for identity in ids) or len(set(ids)) != len(ids):
        raise ValueError("Seller identifiers must be nonblank and unique")
    parent = {identity: identity for identity in ids}

    def root(identity: str) -> str:
        while parent[identity] != identity:
            parent[identity] = parent[parent[identity]]
            identity = parent[identity]
        return identity

    for left, right in links:
        first, second = sorted((root(left), root(right)))
        parent[second] = first
    groups: dict[str, list[str]] = {}
    for identity in ids:
        groups.setdefault(root(identity), []).append(identity)
    return tuple(CopyCluster(identity, tuple(members)) for identity, members in sorted(groups.items()))


def _distinct(values: Sequence[JsonValue]) -> list[JsonValue]:
    """Equality of normalized values, never directional compatibility or tolerance."""
    result: list[JsonValue] = []
    for value in sorted(values, key=db.dumps):
        if not any(value == prior for prior in result):
            result.append(db.loads(db.dumps(value)))
    return result


def _field_consensus(field: str, clusters: tuple[CopyCluster, ...],
                     sellers: Mapping[str, SellerListing]) -> FieldConsensus:
    votes: list[tuple[str, JsonValue]] = []
    abstaining: list[str] = []
    participating = 0
    for cluster in clusters:
        values = _distinct([sellers[identity].values[field] for identity in cluster.seller_ids
                            if sellers[identity].values.get(field) is not None])
        if not values:
            continue
        participating += 1
        if len(values) == 1:
            votes.append((cluster.cluster_id, values[0]))
        else:
            abstaining.append(cluster.cluster_id)
    distinct = _distinct([value for _, value in votes])
    tallies = tuple(ValueVotes(value, tuple(identity for identity, voted in votes if voted == value)) for value in distinct)
    majority = next((entry.value for entry in tallies if len(entry.cluster_ids) * 2 > participating), None)
    outliers: list[str] = []
    if majority is not None:
        for cluster in clusters:
            if cluster.cluster_id in abstaining:
                continue
            for identity in cluster.seller_ids:
                value = sellers[identity].values.get(field)
                if value is not None and not compatible(field, value, majority):
                    outliers.append(identity)
    return FieldConsensus(field, participating, tallies, majority, tuple(sorted(outliers)), tuple(abstaining))


def consensus(listings: Sequence[SellerListing]) -> MarketplaceConsensus:
    """One vote per unambiguous cluster/field; strict majority or no conclusion."""
    clusters = cluster_copies(listings)
    sellers = {item.seller_id: item for item in listings}
    fields = sorted({field for item in listings for field, value in item.values.items() if value is not None})
    return MarketplaceConsensus(clusters, tuple(_field_consensus(field, clusters, sellers) for field in fields))
