"""End-to-end integration tests for the index subpackage.

These exercise the full pipeline: text_records → chunker → fastembed
→ Store → Searcher. They download a small embedding model on first
run, then hit fastembed's local cache thereafter.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastembed")
pytest.importorskip("sqlite_vec")
pytest.importorskip("markitdown")

from crategraph import Crate
from crategraph.index import Indexer, Searcher

FIXTURE = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


@pytest.fixture(scope="module")
def indexed_store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a real index once per module run; reuse for all tests below."""
    store = tmp_path_factory.mktemp("index") / "index.db"
    crate = Crate(str(FIXTURE))
    stats = Indexer(crate, store, progress=False).build()
    assert stats.sources_indexed == ["minimal-crate"]
    assert stats.total_chunks > 0
    return store


def test_search_finds_property_text(indexed_store: Path) -> None:
    hits = Searcher(indexed_store).search("Alice Smith director person", k=5)
    assert hits, "expected at least one hit"
    top_ids = {h.entity_id for h in hits[:3]}
    assert "#alice" in top_ids


def test_search_finds_file_content(indexed_store: Path) -> None:
    hits = Searcher(indexed_store).search("plain text file for testing the inspectors", k=5)
    assert hits
    file_hits = [h for h in hits if h.source_kind == "file"]
    assert file_hits
    assert any(h.entity_id == "sample.txt" for h in file_hits)


def test_filter_by_source_kind(indexed_store: Path) -> None:
    s = Searcher(indexed_store)
    only_files = s.search("sample", k=10, filters={"source_kind": ["file"]})
    only_props = s.search("sample", k=10, filters={"source_kind": ["properties"]})

    assert only_files
    assert only_props
    assert {h.source_kind for h in only_files} == {"file"}
    assert {h.source_kind for h in only_props} == {"properties"}


def test_filter_by_entity_types(indexed_store: Path) -> None:
    hits = Searcher(indexed_store).search("Alice", k=10, filters={"entity_types": ["Person"]})
    assert hits
    for h in hits:
        assert "Person" in h.entity_types


def test_filter_by_source_id(indexed_store: Path) -> None:
    hits = Searcher(indexed_store).search("sample", k=5, filters={"source_id": ["minimal-crate"]})
    assert hits
    assert all(h.source_id == "minimal-crate" for h in hits)


def test_filter_by_entity_id(indexed_store: Path) -> None:
    hits = Searcher(indexed_store).search("anything", k=10, filters={"entity_id": ["#alice"]})
    assert hits
    assert all(h.entity_id == "#alice" for h in hits)


def test_idempotent_rebuild(tmp_path: Path) -> None:
    store = tmp_path / "idem.db"
    crate = Crate(str(FIXTURE))

    first = Indexer(crate, store, progress=False).build()
    assert first.sources_indexed == ["minimal-crate"]

    second = Indexer(crate, store, progress=False).build()
    assert second.sources_indexed == []
    assert second.sources_skipped == ["minimal-crate"]


def test_config_mismatch_refused(tmp_path: Path) -> None:
    store = tmp_path / "mismatch.db"
    crate = Crate(str(FIXTURE))
    Indexer(crate, store, progress=False).build()

    with pytest.raises(ValueError, match="different"):
        Indexer(crate, store, chunk_tokens=999, progress=False).build()


def test_graph_methods_delegate(tmp_path: Path) -> None:
    store = tmp_path / "via_graph.db"
    crate = Crate(str(FIXTURE))

    crate.build_semantic_index(store, progress=False)
    hits = crate.semantic_search("Alice", store_path=store, k=5)
    assert hits
    assert any(h.entity_id == "#alice" for h in hits[:3])


def test_semantic_search_restrict_to_view(tmp_path: Path) -> None:
    """Filtered subgraph should only return hits from its own entities by default."""
    store = tmp_path / "restrict.db"
    crate = Crate(str(FIXTURE))
    crate.build_semantic_index(store, progress=False)

    # Restrict to a single entity via a where filter that should exclude #alice
    just_bob = crate.where(name="Bob Jones")
    assert "#bob" in just_bob._entities
    assert "#alice" not in just_bob._entities

    # Default: restrict_to_view=True
    hits = just_bob.semantic_search("Alice", store_path=store, k=10)
    returned_ids = {h.entity_id for h in hits}
    assert "#alice" not in returned_ids, (
        "view-restricted search should not leak filtered-out entities"
    )

    # Opt out — full index visible
    hits_unrestricted = just_bob.semantic_search(
        "Alice", store_path=store, k=10, restrict_to_view=False
    )
    unrestricted_ids = {h.entity_id for h in hits_unrestricted}
    assert "#alice" in unrestricted_ids


def test_semantic_search_intersects_user_entity_id_with_view(tmp_path: Path) -> None:
    """User-supplied entity_id filters must be intersected with the view.

    A filtered subgraph must not let a caller bypass its restriction by
    naming an entity that's outside the view. The intersection should be
    computed; an empty intersection short-circuits to no hits.
    """
    store = tmp_path / "intersect.db"
    crate = Crate(str(FIXTURE))
    crate.build_semantic_index(store, progress=False)

    just_bob = crate.where(name="Bob Jones")
    assert "#alice" not in just_bob._entities

    # User asks for Alice from a view that excludes her — should be empty,
    # not leak.
    hits = just_bob.semantic_search(
        "Alice", store_path=store, k=10, filters={"entity_id": ["#alice"]}
    )
    assert hits == [], f"view-restricted search must intersect user entity_id filter; got {hits}"

    # User asks for Bob (in view) — intersection is {#bob}, search should
    # still work.
    hits_bob = just_bob.semantic_search(
        "person", store_path=store, k=10, filters={"entity_id": ["#bob"]}
    )
    assert hits_bob, "intersection within the view should still return hits"
    assert all(h.entity_id == "#bob" for h in hits_bob)

    # User asks for {Alice, Bob} from Bob-only view — intersection is {#bob}.
    hits_both = just_bob.semantic_search(
        "anything",
        store_path=store,
        k=10,
        filters={"entity_id": ["#alice", "#bob"]},
    )
    assert hits_both
    assert {h.entity_id for h in hits_both} == {"#bob"}
