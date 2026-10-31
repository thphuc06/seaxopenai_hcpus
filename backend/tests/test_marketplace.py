"""Independent copy votes and conservative outliers on arbitrary normalized inputs."""
from itertools import permutations

import pytest
from pydantic import JsonValue

from app.pipeline.marketplace import SellerListing, cluster_copies, consensus
from app.pipeline.scope import copy_shingles, shingle_jaccard


def seller(identity: str, text: str, value: JsonValue, field: str = "volume") -> SellerListing:
    return SellerListing(identity, text, {field: value})


def volume(value: float) -> dict[str, JsonValue]:
    return {"value": value, "unit": "ml"}


def test_copies_count_once_and_incompatible_outlier_is_separate() -> None:
    copied = "A repeated container specification with its own distinctive description."
    listings = [seller("a", copied, volume(83)), seller("b", copied.upper(), volume(83)),
                seller("c", " \n" + copied + "  ", volume(83)),
                seller("d", "Different prose about packaging and capacity from this merchant.", volume(83)),
                seller("e", "Another entry describes the physical dimensions independently.", volume(121))]
    result = consensus(listings)
    assert len(result.clusters) == 3
    field = result.fields[0]
    assert field.independent_clusters == 3
    assert field.majority == volume(83)
    assert field.outlier_seller_ids == ("e",)
    assert sorted(len(vote.cluster_ids) for vote in field.values) == [1, 2]


def test_union_find_transitive_components_and_exact_threshold() -> None:
    # Unique characters give exact shingle counts: 25/30=0.833 for neighbours;
    # the endpoints share20/30=0.667 and still belong to one component via the middle.
    text = "abcdefghijklmnopqrstuvwxyz01234567"
    listings = [seller("a", text[:29], volume(31)), seller("b", text, volume(31)),
                seller("c", text[5:], volume(31))]
    assert shingle_jaccard(copy_shingles(listings[0].text), copy_shingles(listings[2].text)) < .8
    assert len(cluster_copies(listings)) == 1
    at_boundary = [seller("x", "abcdefgh", volume(31)), seller("y", "abcdefghi", volume(31))]
    assert shingle_jaccard(copy_shingles("abcdefgh"), copy_shingles("abcdefghi")) == .8
    assert len(cluster_copies(at_boundary)) == 1


def test_input_order_and_dictionary_order_do_not_change_consensus() -> None:
    listings = [seller("z", "same description", {"unit": "ml", "value": 37}),
                seller("a", "same description", volume(37.0)),
                seller("m", "unrelated wording", volume(37)), seller("j", "third prose", volume(68))]
    expected = consensus(listings)
    for ordering in permutations(listings):
        assert consensus(ordering) == expected
    assert listings[0].values["volume"] == {"unit": "ml", "value": 37}


@pytest.mark.parametrize("numbers", [(11, 22), (11, 11, 22, 22), (11, 22, 33)])
def test_tie_and_plurality_produce_no_majority_or_outliers(numbers: tuple[int, ...]) -> None:
    result = consensus([seller(str(i), "", volume(value)) for i, value in enumerate(numbers)])
    assert result.fields[0].majority is None
    assert result.fields[0].outlier_seller_ids == ()
    assert len(result.clusters) == len(numbers)


def test_equality_does_not_merge_compatible_volumes() -> None:
    listings = [seller("a", "", volume(100)), seller("b", "", volume(100)),
                seller("c", "", volume(100.5))]
    field = consensus(listings).fields[0]
    assert len(field.values) == 2
    assert field.majority == volume(100)
    assert field.outlier_seller_ids == ()


def test_directional_compatibility_does_not_become_equality() -> None:
    def item(identity: str, types: list[str]) -> SellerListing:
        return seller(identity, "", {"types": types}, "skin_type")
    field = consensus([item("a", ["ALL"]), item("b", ["ALL"]), item("c", ["DRY"])]).fields[0]
    assert len(field.values) == 2 and field.outlier_seller_ids == ()
    reverse = consensus([item("a", ["DRY"]), item("b", ["DRY"]), item("c", ["ALL"])]).fields[0]
    assert reverse.outlier_seller_ids == ("c",)


def test_ambiguous_copy_cluster_abstains_instead_of_multiple_votes_or_outliers() -> None:
    listings = [seller("a", "copied catalogue text", volume(41)),
                seller("b", "copied catalogue text", volume(63)), seller("c", "", volume(41))]
    field = consensus(listings).fields[0]
    assert field.independent_clusters == 2
    assert field.abstaining_cluster_ids == ("a",)
    assert field.majority is None and field.outlier_seller_ids == ()
    listings.extend([seller("d", "", volume(41)), seller("e", "", volume(63))])
    field = consensus(listings).fields[0]
    assert field.majority is None  # Two of four is not a strict majority.


def test_missing_field_does_not_vote_and_empty_input_has_no_conclusion() -> None:
    assert consensus([]).clusters == () and consensus([]).fields == ()
    result = consensus([SellerListing("a", "", {}), seller("b", "", None), seller("c", "", volume(17))])
    assert result.fields[0].independent_clusters == 1
    assert result.fields[0].outlier_seller_ids == ()


@pytest.mark.parametrize("identities", [("same", "same"), ("", "other"), (" ", "other")])
def test_ambiguous_seller_identifiers_are_rejected(identities: tuple[str, str]) -> None:
    with pytest.raises(ValueError, match="identifiers"):
        cluster_copies([seller(identity, "", volume(7)) for identity in identities])
