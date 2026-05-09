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
    result = crate.search("Alice", mode="semantic", store_path=store, k=5)
    assert "#alice" in {e.id for e in result.entities}
    assert len(result.entities) <= 5


def test_semantic_search_restrict_to_view(tmp_path: Path) -> None:
    """Filtered subgraph should only return hits from its own entities by default."""
    store = tmp_path / "restrict.db"
    crate = Crate(str(FIXTURE))
    crate.build_semantic_index(store, progress=False)

    # Restrict to a single entity via a where filter that should exclude #alice
    just_bob = crate.where(name="Bob Jones")
    assert "#bob" in just_bob._entities
    assert "#alice" not in just_bob._entities

    # Default: restrict_to_view=True — view-bounded subgraph
    restricted = just_bob.search("Alice", mode="semantic", store_path=store, k=10)
    returned_ids = {e.id for e in restricted.entities}
    assert "#alice" not in returned_ids, (
        "view-restricted search should not leak filtered-out entities"
    )

    # Opt out — full index visible. This catches the _root._subgraph bug:
    # without the root build path, #alice would be silently dropped because
    # it isn't in just_bob._entities.
    unrestricted = just_bob.search(
        "Alice", mode="semantic", store_path=store, k=10, restrict_to_view=False
    )
    unrestricted_ids = {e.id for e in unrestricted.entities}
    assert "#alice" in unrestricted_ids


def test_indexer_removes_source_when_rebuild_yields_no_text(tmp_path: Path) -> None:
    """A source whose entities exist but produce no text must be deleted on rebuild.

    Today's bug case: text_properties allowlist mismatches every entity
    AND the graph is filtered to exclude data entities — text_units
    becomes empty for an existing source. Without the fix, stale rows
    persist; with the fix, the source is removed.
    """
    store = tmp_path / "stale.db"
    crate = Crate(str(FIXTURE))

    from crategraph.index.store import Store

    # Use a text_properties allowlist pinned to a key all minimal-crate
    # entities actually have, so the initial build populates the index.
    Indexer(crate, store, text_properties=("name",), progress=False).build()
    with Store(store) as s:
        assert "minimal-crate" in s.list_source_ids()

    # Rebuild from a graph that excludes data entities AND uses a
    # property name that doesn't exist on any remaining entity. The
    # source's entities still exist in entities_by_source, but
    # text_units is empty for it. (Need a fresh store path because
    # text_properties is part of the manifest config and changing
    # it mid-stream would be refused.)
    fresh_store = tmp_path / "fresh.db"
    Indexer(crate, fresh_store, text_properties=("__nonexistent__",), progress=False).build()
    no_data = crate.exclude(entity_types=["File"])
    stats = Indexer(
        no_data, fresh_store, text_properties=("__nonexistent__",), progress=False
    ).build()

    assert "minimal-crate" in stats.sources_removed, f"expected source removal, got stats={stats}"
    with Store(fresh_store) as s:
        assert "minimal-crate" not in s.list_source_ids(), (
            "stale source rows should have been deleted"
        )


def test_filtered_search_finds_rare_match_in_large_index(tmp_path: Path) -> None:
    """Filtered KNN must keep growing fetch_k past the historical 6-iteration cap.

    Engineers a synthetic store where 500 chunks all rank near a query,
    but only one chunk passes the filter — and that chunk is at rank
    ~480. The historical cap of 6 doublings (max fetch_k = 320 from
    starting fetch_k = 5) would miss it. With the cap removed, the
    loop expands until fetch_k >= total and the match is found.
    """
    pytest.importorskip("sqlite_vec")
    import numpy as np

    from crategraph.index.models import ChunkSpec, IndexerConfig, TextUnitSpec
    from crategraph.index.store import Store, StoreManifest

    store_path = tmp_path / "rare_filter.db"
    dim = 4
    rng = np.random.default_rng(123)

    units: list[TextUnitSpec] = []
    embeddings_list: list[np.ndarray] = []
    # 499 properties chunks plus one file chunk we want to find via filter.
    for i in range(499):
        text = f"properties text {i}"
        units.append(
            TextUnitSpec(
                source_id="test",
                entity_id=f"prop-{i}",
                entity_types=("Person",),
                source_kind="properties",
                text=text,
                token_count=10,
                chunks=(
                    ChunkSpec(chunk_index=0, char_start=0, char_end=len(text), token_count=10),
                ),
            )
        )
        # Closer to the query (origin) for higher ranks; we want the
        # file row to land beyond the original 320-chunk cap.
        embeddings_list.append(rng.normal(0.0, 0.05, size=dim).astype("float32"))

    # The single matching file chunk — placed slightly farther from the
    # query so it's in the tail beyond the historical cap.
    file_text = "file text 0"
    units.append(
        TextUnitSpec(
            source_id="test",
            entity_id="file-0",
            entity_types=("File",),
            source_kind="file",
            text=file_text,
            token_count=10,
            chunks=(
                ChunkSpec(chunk_index=0, char_start=0, char_end=len(file_text), token_count=10),
            ),
        )
    )
    file_embed = np.array([0.5, 0.5, 0.5, 0.5], dtype="float32")
    embeddings_list.append(file_embed)
    embeddings = np.vstack(embeddings_list)

    manifest = StoreManifest(
        config=IndexerConfig(model="test/synthetic"),
        embedding_dim=dim,
        package_version="test",
        created_at="2025-01-01T00:00:00+00:00",
    )
    with Store(store_path) as store:
        store.initialise(manifest)
        store.replace_source(
            units,
            embeddings,
            source_id="test",
            source_path=None,
            content_hash="x",
            entity_count=500,
        )

    query = np.zeros(dim, dtype="float32")
    with Store(store_path) as store:
        hits = store.vector_search(query, k=1, filters={"source_kind": ["file"]})

    assert len(hits) == 1, "filtered KNN must keep expanding until the matching chunk is found"
    assert hits[0].entity_id == "file-0"


def test_cached_text_records_via_graph(tmp_path: Path) -> None:
    """Graph.text_records(store_path=...) reads from text_units with token_count."""
    store = tmp_path / "cached_text.db"
    crate = Crate(str(FIXTURE))
    crate.build_semantic_index(store, progress=False)

    cached = list(crate.text_records(store_path=store))
    assert cached, "expected cached text records"

    # Cached records carry token_count; live records don't.
    assert all("token_count" in r for r in cached)
    assert all(r["token_count"] > 0 for r in cached)

    live_keys = set(next(iter(crate.text_records())).keys())
    assert "token_count" not in live_keys


def test_cached_text_records_filters(tmp_path: Path) -> None:
    """Filters work end-to-end through Graph → Store on the cached path."""
    store = tmp_path / "cached_filtered.db"
    crate = Crate(str(FIXTURE))
    crate.build_semantic_index(store, progress=False)

    only_files = list(crate.text_records(store_path=store, filters={"source_kind": ["file"]}))
    assert only_files
    assert all(r["source_kind"] == "file" for r in only_files)


def test_chunk_records_reconstructs_text(tmp_path: Path) -> None:
    """Graph.chunk_records yields per-chunk dicts with reconstructed text."""
    store = tmp_path / "chunks.db"
    crate = Crate(str(FIXTURE))
    crate.build_semantic_index(store, progress=False)

    chunks = list(crate.chunk_records(store_path=store))
    assert chunks
    expected_keys = {
        "source_id",
        "entity_id",
        "entity_types",
        "source_kind",
        "chunk_index",
        "char_start",
        "char_end",
        "token_count",
        "text",
    }
    for record in chunks:
        assert set(record.keys()) == expected_keys
        assert record["text"]
        assert record["char_end"] > record["char_start"]


def test_cached_text_records_respects_view(tmp_path: Path) -> None:
    """Filtered subgraph's cached text_records must match the live path."""
    store = tmp_path / "view_text.db"
    crate = Crate(str(FIXTURE))
    crate.build_semantic_index(store, progress=False)

    just_bob = crate.where(name="Bob Jones")
    assert "#bob" in just_bob._entities
    assert "#alice" not in just_bob._entities

    # Default: restrict_to_view=True. Cached path must mirror live path.
    cached = list(just_bob.text_records(store_path=store))
    cached_ids = {r["entity_id"] for r in cached}
    assert "#alice" not in cached_ids, "cached text_records leaked filtered-out entity"
    assert "#bob" in cached_ids

    # Opt out — full index visible.
    full = list(just_bob.text_records(store_path=store, restrict_to_view=False))
    full_ids = {r["entity_id"] for r in full}
    assert "#alice" in full_ids
    assert "#bob" in full_ids


def test_cached_text_records_intersects_user_entity_id_filter(tmp_path: Path) -> None:
    """User-supplied entity_id must be intersected with the view, not replace it."""
    store = tmp_path / "view_intersect_text.db"
    crate = Crate(str(FIXTURE))
    crate.build_semantic_index(store, progress=False)

    just_bob = crate.where(name="Bob Jones")

    # Asking for Alice from a Bob-only view yields nothing.
    nothing = list(just_bob.text_records(store_path=store, filters={"entity_id": ["#alice"]}))
    assert nothing == []

    # Asking for Bob (in view) still works.
    bob = list(just_bob.text_records(store_path=store, filters={"entity_id": ["#bob"]}))
    assert bob
    assert all(r["entity_id"] == "#bob" for r in bob)


def test_chunk_records_respects_view(tmp_path: Path) -> None:
    """chunk_records must intersect with the view, same as text_records."""
    store = tmp_path / "view_chunks.db"
    crate = Crate(str(FIXTURE))
    crate.build_semantic_index(store, progress=False)

    just_bob = crate.where(name="Bob Jones")

    # Default restriction should hide #alice's chunks.
    chunks = list(just_bob.chunk_records(store_path=store))
    chunk_ids = {c["entity_id"] for c in chunks}
    assert "#alice" not in chunk_ids
    assert "#bob" in chunk_ids

    # Opt-out reveals everything.
    full = list(just_bob.chunk_records(store_path=store, restrict_to_view=False))
    assert "#alice" in {c["entity_id"] for c in full}


def test_default_index_path_for_single_crate() -> None:
    """Single-source graphs default to <cwd>/.crategraph/<source_id>.db."""
    from pathlib import Path as _Path

    crate = Crate(str(FIXTURE))
    expected = _Path.cwd() / ".crategraph" / "minimal-crate.db"
    assert crate.default_index_path == expected


def test_default_index_path_for_multi_source_uses_hash(tmp_path: Path) -> None:
    """Multi-source graphs default to <cwd>/.crategraph/corpus-<sha8>.db."""
    second = Path(__file__).parent.parent / "fixtures" / "second-crate"
    if not second.exists():
        pytest.skip("second-crate fixture missing")
    crate = Crate(str(FIXTURE), str(second))
    p = crate.default_index_path
    assert p.parent.name == ".crategraph"
    assert p.name.startswith("corpus-")
    assert p.suffix == ".db"
    # Stable: same paths produce the same hash.
    again = Crate(str(FIXTURE), str(second))
    assert crate.default_index_path == again.default_index_path


def test_default_index_path_raises_when_no_source(tmp_path: Path) -> None:
    """Graph with no source can't derive a default path."""
    from crategraph.core.graph import Graph

    g = Graph()
    with pytest.raises(ValueError, match="no source"):
        _ = g.default_index_path


def test_build_and_search_use_default_path(tmp_path: Path, monkeypatch) -> None:
    """End-to-end: build_semantic_index() and search(mode="semantic") with no args."""
    monkeypatch.chdir(tmp_path)
    crate = Crate(str(FIXTURE))

    expected = tmp_path / ".crategraph" / "minimal-crate.db"
    assert not expected.exists()

    crate.build_semantic_index(progress=False)
    assert expected.exists(), "build should have created the default index"

    result = crate.search("Alice", mode="semantic", k=3)
    assert "#alice" in {e.id for e in result.entities}


def test_search_without_index_raises_helpful_error(tmp_path: Path, monkeypatch) -> None:
    """Calling search(mode="semantic") before build raises a clear error."""
    monkeypatch.chdir(tmp_path)
    crate = Crate(str(FIXTURE))

    with pytest.raises(FileNotFoundError, match="default location"):
        crate.search("anything", mode="semantic", k=1)


def test_chunk_records_uses_default_path(tmp_path: Path, monkeypatch) -> None:
    """chunk_records() with no store_path falls back to default."""
    monkeypatch.chdir(tmp_path)
    crate = Crate(str(FIXTURE))
    crate.build_semantic_index(progress=False)

    records = list(crate.chunk_records())
    assert records


def test_explicit_store_path_overrides_default(tmp_path: Path, monkeypatch) -> None:
    """Explicit store_path always wins, even if default would point elsewhere."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    custom = tmp_path / "custom-name.db"
    crate = Crate(str(FIXTURE))
    crate.build_semantic_index(custom, progress=False)

    assert custom.exists()
    # Default location should NOT have been touched.
    assert not (elsewhere / ".crategraph" / "minimal-crate.db").exists()

    result = crate.search("Alice", mode="semantic", store_path=custom, k=3)
    assert "#alice" in {e.id for e in result.entities}


def test_search_invalid_mode_raises(tmp_path: Path) -> None:
    """An unknown mode= value must error rather than silently no-op."""
    crate = Crate(str(FIXTURE))
    with pytest.raises(ValueError, match="Unknown search mode"):
        crate.search("anything", mode="invalid")


def test_search_unrelated_index_warns(tmp_path: Path) -> None:
    """Searching against an index built for a different crate emits a warning."""
    import warnings

    second = Path(__file__).parent.parent / "fixtures" / "second-crate"
    if not second.exists():
        pytest.skip("second-crate fixture missing")

    # Build an index against a *different* crate.
    other_store = tmp_path / "second.db"
    Crate(str(second)).build_semantic_index(other_store, progress=False)

    # Now search from the minimal-crate against that unrelated index.
    crate = Crate(str(FIXTURE))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        crate.search("anything", mode="semantic", store_path=other_store, k=1)

    assert any("don't overlap" in str(w.message) for w in caught), (
        f"expected source-mismatch warning; got: {[str(w.message) for w in caught]}"
    )


def test_chunk_records_with_query_returns_ranked_records(tmp_path: Path) -> None:
    """chunk_records(query=...) yields scored records ranked by relevance."""
    store = tmp_path / "ranked.db"
    crate = Crate(str(FIXTURE))
    crate.build_semantic_index(store, progress=False)

    records = list(crate.chunk_records("Alice Smith director", store_path=store, k=5))
    assert records, "expected ranked chunk records"

    # Scores must be descending (higher is more relevant).
    scores = [r["score"] for r in records]
    assert scores == sorted(scores, reverse=True)

    # Top hit should be Alice's chunk.
    top_ids = {r["entity_id"] for r in records[:3]}
    assert "#alice" in top_ids

    # Records carry chunk-level provenance fields plus score.
    expected_keys = {
        "source_id",
        "entity_id",
        "entity_types",
        "source_kind",
        "chunk_index",
        "char_start",
        "char_end",
        "token_count",
        "text",
        "score",
    }
    assert set(records[0].keys()) == expected_keys


def test_chunk_records_without_query_unchanged(tmp_path: Path) -> None:
    """chunk_records() with no query still does the full unranked iteration."""
    store = tmp_path / "iter.db"
    crate = Crate(str(FIXTURE))
    crate.build_semantic_index(store, progress=False)

    records = list(crate.chunk_records(store_path=store))
    assert records
    # No score field on unranked records.
    assert "score" not in records[0]


def test_ranked_chunk_records_respects_view(tmp_path: Path) -> None:
    """Ranked chunk_records also intersects with the current graph view."""
    store = tmp_path / "ranked_view.db"
    crate = Crate(str(FIXTURE))
    crate.build_semantic_index(store, progress=False)

    just_bob = crate.where(name="Bob Jones")

    records = list(just_bob.chunk_records("Alice", store_path=store, k=10))
    returned_ids = {r["entity_id"] for r in records}
    assert "#alice" not in returned_ids, "ranked chunk_records must intersect with the view"


def test_chunk_records_text_matches_text_units(tmp_path: Path) -> None:
    """Reconstructed chunk text must equal the SUBSTR of the parent text_unit."""
    store = tmp_path / "verify.db"
    crate = Crate(str(FIXTURE))
    crate.build_semantic_index(store, progress=False)

    units = {
        (r["entity_id"], r["source_kind"]): r["text"] for r in crate.text_records(store_path=store)
    }
    for chunk in crate.chunk_records(store_path=store):
        key = (chunk["entity_id"], chunk["source_kind"])
        unit_text = units[key]
        expected = unit_text[chunk["char_start"] : chunk["char_end"]]
        assert chunk["text"] == expected, (
            f"chunk text mismatch for {key} idx={chunk['chunk_index']}"
        )


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
    result = just_bob.search(
        "Alice",
        mode="semantic",
        store_path=store,
        k=10,
        filters={"entity_id": ["#alice"]},
    )
    assert list(result.entities) == [], (
        f"view-restricted search must intersect user entity_id filter; got {list(result.entities)}"
    )

    # User asks for Bob (in view) — intersection is {#bob}, search should
    # still work.
    result_bob = just_bob.search(
        "person",
        mode="semantic",
        store_path=store,
        k=10,
        filters={"entity_id": ["#bob"]},
    )
    assert "#bob" in {e.id for e in result_bob.entities}

    # User asks for {Alice, Bob} from Bob-only view — intersection is {#bob}.
    result_both = just_bob.search(
        "anything",
        mode="semantic",
        store_path=store,
        k=10,
        filters={"entity_id": ["#alice", "#bob"]},
    )
    assert {e.id for e in result_both.entities} == {"#bob"}
