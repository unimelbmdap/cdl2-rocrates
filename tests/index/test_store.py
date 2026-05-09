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

from crategraph.index.models import (
    ChunkSpec,
    IndexerConfig,
    TextUnitSpec,
)
from crategraph.index.store import Store, StoreManifest

DIM = 4


def _make_manifest(dim: int = DIM) -> StoreManifest:
    return StoreManifest(
        config=IndexerConfig(model="test/synthetic"),
        embedding_dim=dim,
        package_version="test",
        created_at="2025-01-01T00:00:00+00:00",
    )


def _unit(idx: int, source_kind: str, *, source_id: str = "test") -> TextUnitSpec:
    """Build a synthetic single-chunk text unit."""
    text = f"{source_kind} text {idx}"
    return TextUnitSpec(
        source_id=source_id,
        entity_id=f"{source_kind}-{idx}",
        entity_types=("Person",) if source_kind == "properties" else ("File",),
        source_kind=source_kind,  # type: ignore[arg-type]
        text=text,
        token_count=10,
        chunks=(
            ChunkSpec(
                chunk_index=0,
                char_start=0,
                char_end=len(text),
                token_count=10,
            ),
        ),
    )


def test_filtered_search_iterates_past_initial_window(tmp_path: Path) -> None:
    """Filters that eliminate the global top-fetch_k must still return k hits."""
    store_path = tmp_path / "synth.db"

    rng = np.random.default_rng(42)
    units: list[TextUnitSpec] = []
    embeddings_list: list[np.ndarray] = []

    for i in range(25):
        units.append(_unit(i, "properties"))
        embeddings_list.append(rng.normal(0.0, 0.05, size=DIM).astype("float32"))
    for i in range(5):
        units.append(_unit(i, "file"))
        far_vec = rng.normal(0.0, 0.05, size=DIM).astype("float32")
        far_vec += np.array([5.0, 0.0, 0.0, 0.0], dtype="float32")
        embeddings_list.append(far_vec)
    embeddings = np.vstack(embeddings_list)

    with Store(store_path) as store:
        store.initialise(_make_manifest())
        store.replace_source(
            units,
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
    units = [_unit(i, "properties") for i in range(20)]
    embeddings = rng.normal(0.0, 1.0, size=(20, DIM)).astype("float32")

    with Store(store_path) as store:
        store.initialise(_make_manifest())
        store.replace_source(
            units,
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
    """Re-inserting a source id must wipe the old text_units/chunks/vec rows."""
    store_path = tmp_path / "replace.db"

    rng = np.random.default_rng(7)
    first_units = [_unit(i, "properties") for i in range(10)]
    first_embeddings = rng.normal(0.0, 1.0, size=(10, DIM)).astype("float32")

    second_units = [_unit(i, "file") for i in range(3)]
    second_embeddings = rng.normal(0.0, 1.0, size=(3, DIM)).astype("float32")

    with Store(store_path) as store:
        store.initialise(_make_manifest())
        store.replace_source(
            first_units,
            first_embeddings,
            source_id="test",
            source_path=None,
            content_hash="hash-1",
            entity_count=10,
        )
        store.replace_source(
            second_units,
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
        text_units_count = store.conn.execute(
            "SELECT COUNT(*) FROM text_units WHERE source_id = ?", ("test",)
        ).fetchone()[0]
        vec_count = store.conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
        assert chunks_count == 3
        assert text_units_count == 3, "old text_units rows must be cleared on replace"
        assert vec_count == 3, "old vec_chunks rows must be cleared on replace"


def test_unsupported_filter_raises(tmp_path: Path) -> None:
    """Unknown filter keys should error rather than silently no-op."""
    store_path = tmp_path / "filter.db"
    rng = np.random.default_rng(1)
    with Store(store_path) as store:
        store.initialise(_make_manifest())
        store.replace_source(
            [_unit(0, "properties")],
            rng.normal(0.0, 1.0, size=(1, DIM)).astype("float32"),
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
    """Explicit empty filter values mean "match nothing", not "no filter"."""
    store_path = tmp_path / "empty_filter.db"
    rng = np.random.default_rng(11)
    units = [_unit(i, "properties") for i in range(10)]
    embeddings = rng.normal(0.0, 1.0, size=(10, DIM)).astype("float32")

    with Store(store_path) as store:
        store.initialise(_make_manifest())
        store.replace_source(
            units,
            embeddings,
            source_id="test",
            source_path=None,
            content_hash="x",
            entity_count=10,
        )

    query = np.zeros(DIM, dtype="float32")
    with Store(store_path) as store:
        baseline = store.vector_search(query, k=5)
        assert baseline

        for key in ("source_id", "entity_id", "source_kind", "entity_types"):
            hits = store.vector_search(query, k=5, filters={key: []})
            assert hits == [], f"empty {key!r} filter must return [], got {hits}"

        passthrough = store.vector_search(
            query,
            k=5,
            filters={"entity_id": None, "source_kind": ["properties"]},  # type: ignore[dict-item]
        )
        assert passthrough


def test_iter_text_records_returns_text_units(tmp_path: Path) -> None:
    """iter_text_records yields one record per text unit with token_count."""
    store_path = tmp_path / "iter_text.db"
    rng = np.random.default_rng(3)
    units = [_unit(i, "properties") for i in range(5)] + [_unit(i, "file") for i in range(3)]
    embeddings = rng.normal(0.0, 1.0, size=(8, DIM)).astype("float32")

    with Store(store_path) as store:
        store.initialise(_make_manifest())
        store.replace_source(
            units,
            embeddings,
            source_id="test",
            source_path=None,
            content_hash="x",
            entity_count=8,
        )

    with Store(store_path) as store:
        records = list(store.iter_text_records())

    assert len(records) == 8
    keys = set(records[0].keys())
    assert keys == {
        "source_id",
        "entity_id",
        "entity_types",
        "source_kind",
        "text",
        "token_count",
    }
    assert all(r["source_id"] == "test" for r in records)
    assert {r["source_kind"] for r in records} == {"properties", "file"}


def test_iter_chunk_records_reconstructs_text_via_substr(tmp_path: Path) -> None:
    """iter_chunk_records reconstructs the chunk text from offsets + SUBSTR."""
    store_path = tmp_path / "iter_chunk.db"
    rng = np.random.default_rng(5)

    # Build a multi-chunk text unit so we exercise non-trivial offsets.
    full_text = " ".join(f"word{i:04d}" for i in range(40))
    chunks = (
        ChunkSpec(chunk_index=0, char_start=0, char_end=100, token_count=15),
        ChunkSpec(chunk_index=1, char_start=80, char_end=200, token_count=18),
        ChunkSpec(chunk_index=2, char_start=180, char_end=len(full_text), token_count=18),
    )
    unit = TextUnitSpec(
        source_id="test",
        entity_id="big-doc",
        entity_types=("File",),
        source_kind="file",
        text=full_text,
        token_count=51,
        chunks=chunks,
    )
    embeddings = rng.normal(0.0, 1.0, size=(3, DIM)).astype("float32")

    with Store(store_path) as store:
        store.initialise(_make_manifest())
        store.replace_source(
            [unit],
            embeddings,
            source_id="test",
            source_path=None,
            content_hash="x",
            entity_count=1,
        )

    with Store(store_path) as store:
        records = list(store.iter_chunk_records())

    assert len(records) == 3
    for record, spec in zip(records, chunks, strict=True):
        assert record["chunk_index"] == spec.chunk_index
        assert record["char_start"] == spec.char_start
        assert record["char_end"] == spec.char_end
        # The reconstructed text must match Python slicing of the canonical text.
        expected = full_text[spec.char_start : spec.char_end]
        assert record["text"] == expected, (
            f"chunk {spec.chunk_index}: SUBSTR returned {record['text']!r}, expected {expected!r}"
        )


def test_filter_handles_lists_larger_than_sqlite_bind_limit(tmp_path: Path) -> None:
    """entity_id (and source_id) filters must not bind one parameter per id.

    SQLite's default bind limit is 999 on older builds, 32 766 on
    recent ones; either way, a derived view of a large crate can produce
    an entity_id list that exceeds it. The fix routes list filters
    through a single JSON parameter expanded via ``json_each``, so any
    list size works.
    """
    store_path = tmp_path / "big_filter.db"
    rng = np.random.default_rng(17)

    # 1500 entities — well above SQLite's old 999 bind limit.
    n = 1500
    units = [_unit(i, "properties") for i in range(n)]
    embeddings = rng.normal(0.0, 1.0, size=(n, DIM)).astype("float32")

    with Store(store_path) as store:
        store.initialise(_make_manifest())
        store.replace_source(
            units,
            embeddings,
            source_id="test",
            source_path=None,
            content_hash="x",
            entity_count=n,
        )

    query = np.zeros(DIM, dtype="float32")
    all_entity_ids = [f"properties-{i}" for i in range(n)]

    with Store(store_path) as store:
        # Pre-fix this would raise ``OperationalError: too many SQL
        # variables`` on older SQLite builds; with json_each it succeeds.
        hits = store.vector_search(
            query,
            k=5,
            filters={"entity_id": all_entity_ids},
        )
        assert hits, "expected hits when filter covers every entity"
        assert len(hits) == 5

        # iter_text_records and iter_chunk_records use the same
        # filter builder; verify they survive the same input.
        text_records = list(store.iter_text_records(filters={"entity_id": all_entity_ids}))
        assert len(text_records) == n


def test_iter_text_records_filtered(tmp_path: Path) -> None:
    """Filters on iter_text_records narrow the result set."""
    store_path = tmp_path / "iter_text_filtered.db"
    rng = np.random.default_rng(9)
    units = [_unit(i, "properties") for i in range(3)] + [_unit(i, "file") for i in range(2)]
    embeddings = rng.normal(0.0, 1.0, size=(5, DIM)).astype("float32")

    with Store(store_path) as store:
        store.initialise(_make_manifest())
        store.replace_source(
            units,
            embeddings,
            source_id="test",
            source_path=None,
            content_hash="x",
            entity_count=5,
        )

    with Store(store_path) as store:
        only_files = list(store.iter_text_records(filters={"source_kind": ["file"]}))
        assert len(only_files) == 2
        assert all(r["source_kind"] == "file" for r in only_files)

        # Empty filter short-circuits.
        nothing = list(store.iter_text_records(filters={"source_kind": []}))
        assert nothing == []

        # entity_id filter targets a specific record.
        targeted = list(store.iter_text_records(filters={"entity_id": ["properties-0"]}))
        assert len(targeted) == 1
        assert targeted[0]["entity_id"] == "properties-0"
