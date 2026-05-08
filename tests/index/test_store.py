"""Store-level unit tests with hand-crafted vectors.

Bypasses the embedder so we can deterministically engineer cases that
exercise the iterative-fetch logic for filtered search and the atomic
replace behaviour of ``replace_source``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("sqlite_vec")
import numpy as np

from crategraph.index.models import Chunk, IndexerConfig
from crategraph.index.store import Store, StoreManifest

DIM = 4


def _make_manifest(dim: int = DIM) -> StoreManifest:
    return StoreManifest(
        config=IndexerConfig(model="test/synthetic"),
        embedding_dim=dim,
        package_version="test",
        created_at="2025-01-01T00:00:00+00:00",
    )


def _make_chunk(idx: int, source_kind: str) -> Chunk:
    return Chunk(
        source_id="test",
        entity_id=f"{source_kind}-{idx}",
        entity_types=("Person",) if source_kind == "properties" else ("File",),
        source_kind=source_kind,  # type: ignore[arg-type]
        chunk_index=0,
        token_count=10,
        text=f"{source_kind} chunk {idx}",
    )


def test_filtered_search_iterates_past_initial_window(tmp_path: Path) -> None:
    """Filters that eliminate the global top-fetch_k must still return k hits."""
    store_path = tmp_path / "synth.db"

    rng = np.random.default_rng(42)
    chunks: list[Chunk] = []
    embeddings_list: list[np.ndarray] = []

    for i in range(25):
        chunks.append(_make_chunk(i, "properties"))
        embeddings_list.append(rng.normal(0.0, 0.05, size=DIM).astype("float32"))
    for i in range(5):
        chunks.append(_make_chunk(i, "file"))
        far_vec = rng.normal(0.0, 0.05, size=DIM).astype("float32")
        far_vec += np.array([5.0, 0.0, 0.0, 0.0], dtype="float32")
        embeddings_list.append(far_vec)
    embeddings = np.vstack(embeddings_list)

    with Store(store_path) as store:
        store.initialise(_make_manifest())
        store.replace_source(
            chunks,
            embeddings,
            source_id="test",
            source_path="/test",
            content_hash="hash-1",
            entity_count=30,
        )

    query = np.zeros(DIM, dtype="float32")
    with Store(store_path) as store:
        hits = store.vector_search(query, k=5, filters={"source_kind": ["file"]})

    assert len(hits) == 5, f"expected 5 file hits, got {len(hits)}: {hits}"
    assert all(h.source_kind == "file" for h in hits)


def test_unfiltered_search_returns_exact_k(tmp_path: Path) -> None:
    """Without filters, the KNN should return precisely the k closest rows."""
    store_path = tmp_path / "exact.db"

    rng = np.random.default_rng(0)
    chunks = [_make_chunk(i, "properties") for i in range(20)]
    embeddings = rng.normal(0.0, 1.0, size=(20, DIM)).astype("float32")

    with Store(store_path) as store:
        store.initialise(_make_manifest())
        store.replace_source(
            chunks,
            embeddings,
            source_id="test",
            source_path=None,
            content_hash="x",
            entity_count=20,
        )

    query = np.zeros(DIM, dtype="float32")
    with Store(store_path) as store:
        hits = store.vector_search(query, k=7)

    assert len(hits) == 7
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_replace_source_clears_old_rows_atomically(tmp_path: Path) -> None:
    """Re-inserting a source id must wipe the old chunks/vec rows entirely."""
    store_path = tmp_path / "replace.db"

    rng = np.random.default_rng(7)
    first_chunks = [_make_chunk(i, "properties") for i in range(10)]
    first_embeddings = rng.normal(0.0, 1.0, size=(10, DIM)).astype("float32")

    second_chunks = [_make_chunk(i, "file") for i in range(3)]
    second_embeddings = rng.normal(0.0, 1.0, size=(3, DIM)).astype("float32")

    with Store(store_path) as store:
        store.initialise(_make_manifest())
        store.replace_source(
            first_chunks,
            first_embeddings,
            source_id="test",
            source_path=None,
            content_hash="hash-1",
            entity_count=10,
        )
        store.replace_source(
            second_chunks,
            second_embeddings,
            source_id="test",
            source_path=None,
            content_hash="hash-2",
            entity_count=3,
        )

    with Store(store_path) as store:
        record = store.get_source_record("test")
        assert record is not None
        assert record.chunk_count == 3
        assert record.entity_count == 3
        assert record.content_hash == "hash-2"

        chunks_count = store.conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE source_id = ?", ("test",)
        ).fetchone()[0]
        vec_count = store.conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
        assert chunks_count == 3
        assert vec_count == 3, "old vec_chunks rows must be cleared on replace"


def test_unsupported_filter_raises(tmp_path: Path) -> None:
    """Unknown filter keys should error rather than silently no-op."""
    store_path = tmp_path / "filter.db"
    with Store(store_path) as store:
        store.initialise(_make_manifest())
        store.replace_source(
            [_make_chunk(0, "properties")],
            np.zeros((1, DIM), dtype="float32"),
            source_id="test",
            source_path=None,
            content_hash="x",
            entity_count=1,
        )

    with Store(store_path) as store, pytest.raises(ValueError, match="Unsupported filter key"):
        store.vector_search(
            np.zeros(DIM, dtype="float32"),
            k=5,
            filters={"bogus": ["x"]},
        )


def test_empty_filter_value_returns_no_hits(tmp_path: Path) -> None:
    """Explicit empty filter values mean "match nothing", not "no filter".

    The historical bug was treating ``[]`` and ``None`` identically and
    silently dropping the constraint. Now an empty sequence
    short-circuits to zero results.
    """
    store_path = tmp_path / "empty_filter.db"
    rng = np.random.default_rng(11)
    chunks = [_make_chunk(i, "properties") for i in range(10)]
    embeddings = rng.normal(0.0, 1.0, size=(10, DIM)).astype("float32")

    with Store(store_path) as store:
        store.initialise(_make_manifest())
        store.replace_source(
            chunks,
            embeddings,
            source_id="test",
            source_path=None,
            content_hash="x",
            entity_count=10,
        )

    query = np.zeros(DIM, dtype="float32")
    with Store(store_path) as store:
        # Sanity: no filter returns hits.
        baseline = store.vector_search(query, k=5)
        assert baseline

        # Explicit empty list on each filter key returns nothing.
        for key in ("source_id", "entity_id", "source_kind", "entity_types"):
            hits = store.vector_search(query, k=5, filters={key: []})
            assert hits == [], f"empty {key!r} filter must return [], got {hits}"

        # ``None`` value means "no filter for this key" — should still hit.
        # (Pass alongside a real filter so we know None is being ignored,
        # not short-circuiting.)
        passthrough = store.vector_search(
            query,
            k=5,
            filters={"entity_id": None, "source_kind": ["properties"]},  # type: ignore[dict-item]
        )
        assert passthrough, "None values should mean 'no filter for this key'"
