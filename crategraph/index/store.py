"""SQLite + sqlite-vec persistence for the index.

This module is the **sole owner of SQL** in the package. All SQL
strings live as named module-level ``_SQL_*`` constants below, and
public callers interact via typed methods on ``Store``. Other modules
(indexer, searcher, hashing, the graph delegations) must never embed
SQL — if a new query is needed, add a method here.

Schema overview
---------------

``text_units`` holds canonical extracted text — one row per source
unit (a file's content, or an entity's properties block). ``chunks``
stores only offsets into the corresponding text_unit (``char_start``,
``char_end``) plus a denormalised ``source_id`` for fast filtering;
chunks have no text column. ``vec_chunks`` (sqlite-vec virtual table)
keys vectors by ``rowid = chunks.chunk_id``. Chunk text is
reconstructed at query time via ``SUBSTR(text_units.text, ...)``.

This eliminates the ~17% overlap-duplication that a chunks-with-text
schema otherwise carries, and gives ``text_records`` a single, clean
read path.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from crategraph.index.models import (
    IndexerConfig,
    SearchHit,
    SourceRecord,
    TextUnitSpec,
)

if TYPE_CHECKING:
    import numpy as np


# ---------------------------------------------------------------------------
# SQL — every query in the package lives here.
# ---------------------------------------------------------------------------

_SQL_SCHEMA = """
CREATE TABLE IF NOT EXISTS manifest (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    source_path TEXT,
    content_hash TEXT NOT NULL,
    entity_count INTEGER NOT NULL,
    chunk_count INTEGER NOT NULL,
    indexed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS text_units (
    text_unit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    entity_types TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    text TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(source_id)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_text_units_source_entity
    ON text_units(source_id, entity_id);
CREATE INDEX IF NOT EXISTS idx_text_units_source_kind
    ON text_units(source_kind);
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
    text_unit_id INTEGER NOT NULL,
    source_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    token_count INTEGER NOT NULL,
    FOREIGN KEY (text_unit_id) REFERENCES text_units(text_unit_id)
        ON DELETE CASCADE,
    UNIQUE (text_unit_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_chunks_text_unit
    ON chunks(text_unit_id);
CREATE INDEX IF NOT EXISTS idx_chunks_source
    ON chunks(source_id);
"""

_SQL_CREATE_VEC_TABLE = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding float[{dim}])"
)

_SQL_UPSERT_MANIFEST = "INSERT OR REPLACE INTO manifest(key, value) VALUES (?, ?)"

_SQL_GET_MANIFEST = "SELECT value FROM manifest WHERE key = ?"

_SQL_HAS_MANIFEST_TABLE = "SELECT 1 FROM sqlite_master WHERE type='table' AND name='manifest'"

_SQL_GET_SOURCE = "SELECT * FROM sources WHERE source_id = ?"

_SQL_LIST_SOURCE_IDS = "SELECT source_id FROM sources ORDER BY source_id"

# vec_chunks isn't FK-linked, so we delete its rows by their rowids
# (== chunks.chunk_id) inside the same transaction as the delete on
# chunks/text_units/sources. ``chunks.source_id`` is denormalised so
# this query stays a flat subquery, no JOIN through text_units required.
_SQL_DELETE_VEC_FOR_SOURCE = (
    "DELETE FROM vec_chunks WHERE rowid IN (SELECT chunk_id FROM chunks WHERE source_id = ?)"
)

_SQL_DELETE_CHUNKS_FOR_SOURCE = "DELETE FROM chunks WHERE source_id = ?"

_SQL_DELETE_TEXT_UNITS_FOR_SOURCE = "DELETE FROM text_units WHERE source_id = ?"

_SQL_DELETE_SOURCE = "DELETE FROM sources WHERE source_id = ?"

_SQL_UPSERT_SOURCE = (
    "INSERT OR REPLACE INTO sources"
    "(source_id, source_path, content_hash, entity_count, chunk_count, indexed_at) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)

_SQL_INSERT_TEXT_UNIT = (
    "INSERT INTO text_units"
    "(source_id, entity_id, entity_types, source_kind, text, token_count) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)

_SQL_INSERT_CHUNK = (
    "INSERT INTO chunks"
    "(text_unit_id, source_id, chunk_index, char_start, char_end, token_count) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)

_SQL_INSERT_VEC = "INSERT INTO vec_chunks(rowid, embedding) VALUES (?, ?)"

_SQL_COUNT_CHUNKS = "SELECT COUNT(*) FROM chunks"

# Vector search template — `{filter_sql}` is filled in safely by
# _build_filter_clause(), which only emits placeholders, never values.
# Chunk text is reconstructed via SUBSTR over text_units.text.
_SQL_VECTOR_SEARCH_TEMPLATE = (
    "WITH knn AS ("
    "  SELECT rowid, distance "
    "  FROM vec_chunks "
    "  WHERE embedding MATCH ? AND k = ?"
    ") "
    "SELECT "
    "  c.source_id, "
    "  t.entity_id, "
    "  t.entity_types, "
    "  t.source_kind, "
    "  c.chunk_index, "
    "  c.char_start, "
    "  c.char_end, "
    "  c.token_count, "
    "  SUBSTR(t.text, c.char_start + 1, c.char_end - c.char_start) AS text, "
    "  knn.distance "
    "FROM knn "
    "JOIN chunks c ON c.chunk_id = knn.rowid "
    "JOIN text_units t ON t.text_unit_id = c.text_unit_id"
    "{filter_sql} "
    "ORDER BY knn.distance "
    "LIMIT ?"
)

_SQL_ITER_TEXT_RECORDS_TEMPLATE = (
    "SELECT t.source_id, t.entity_id, t.entity_types, t.source_kind, "
    "  t.text, t.token_count "
    "FROM text_units t"
    "{filter_sql} "
    "ORDER BY t.source_id, t.entity_id, t.source_kind"
)

_SQL_ITER_CHUNK_RECORDS_TEMPLATE = (
    "SELECT "
    "  c.source_id, "
    "  t.entity_id, "
    "  t.entity_types, "
    "  t.source_kind, "
    "  c.chunk_index, "
    "  c.char_start, "
    "  c.char_end, "
    "  c.token_count, "
    "  SUBSTR(t.text, c.char_start + 1, c.char_end - c.char_start) AS text "
    "FROM chunks c "
    "JOIN text_units t ON t.text_unit_id = c.text_unit_id"
    "{filter_sql} "
    "ORDER BY c.source_id, t.entity_id, t.source_kind, c.chunk_index"
)


# ---------------------------------------------------------------------------
# Connection + manifest support
# ---------------------------------------------------------------------------


def _connect(path: str):
    """Return a SQLite connection that supports extension loading.

    Python's bundled ``sqlite3`` is sometimes built without extension
    loading — notably the default builds shipped by pyenv on macOS,
    Apple's system Python, and some Linux distros. ``sqlite-vec``
    requires extension loading. If unavailable, we raise an actionable
    error pointing at the easy fixes.

    Recommended fixes (any one):

    1. Use a uv-managed Python (``uv python install 3.12``); these
       are built with extension loading enabled.
    2. Install ``pysqlite3-binary`` — has wheels for Linux (and a
       source distribution for other platforms with build tools).
    3. Rebuild your interpreter with
       ``--enable-loadable-sqlite-extensions``.
    """
    sqlite_mod = None
    try:
        import pysqlite3 as sqlite_mod  # type: ignore[import-not-found,no-redef]
    except ImportError:
        import sqlite3 as sqlite_mod  # type: ignore[no-redef]

    conn = sqlite_mod.connect(path)
    if not hasattr(conn, "enable_load_extension"):
        conn.close()
        msg = (
            "Your Python's sqlite3 was built without extension loading, "
            "which sqlite-vec requires. Easiest fix: use a uv-managed "
            "Python (uv python install 3.12, then recreate the venv). "
            "Alternative: pip install pysqlite3-binary."
        )
        raise RuntimeError(msg)
    conn.row_factory = sqlite_mod.Row
    return conn


@dataclass
class StoreManifest:
    """The on-disk manifest contents."""

    config: IndexerConfig
    embedding_dim: int
    package_version: str
    created_at: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "config": self.config.to_dict(),
                "embedding_dim": self.embedding_dim,
                "package_version": self.package_version,
                "created_at": self.created_at,
            },
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, raw: str) -> StoreManifest:
        data = json.loads(raw)
        return cls(
            config=IndexerConfig.from_dict(data["config"]),
            embedding_dim=data["embedding_dim"],
            package_version=data["package_version"],
            created_at=data["created_at"],
        )


# ---------------------------------------------------------------------------
# Filter clause builder
# ---------------------------------------------------------------------------

_FILTER_KEYS_SUPPORTED = {"source_id", "entity_id", "entity_types", "source_kind"}

# Column maps tell _build_filter_clause which table-qualified column
# corresponds to each filter key for a given query shape.
_FILTER_COLUMNS_VECTOR_SEARCH: dict[str, str] = {
    "source_id": "c.source_id",
    "entity_id": "t.entity_id",
    "source_kind": "t.source_kind",
    "entity_types": "t.entity_types",
}

_FILTER_COLUMNS_TEXT_UNITS: dict[str, str] = {
    "source_id": "t.source_id",
    "entity_id": "t.entity_id",
    "source_kind": "t.source_kind",
    "entity_types": "t.entity_types",
}

_FILTER_COLUMNS_CHUNKS: dict[str, str] = {
    "source_id": "c.source_id",
    "entity_id": "t.entity_id",
    "source_kind": "t.source_kind",
    "entity_types": "t.entity_types",
}


def _build_filter_clause(
    filters: Mapping[str, Sequence[str]] | None,
    columns: Mapping[str, str],
) -> tuple[str, list[Any]]:
    """Return (sql_fragment, params) for the optional WHERE clause.

    Caller composes the fragment into the prepared template; values
    are returned as a separate parameter list so they're bound, not
    interpolated. ``columns`` maps filter keys to the appropriate
    table-qualified column name for the query being assembled.
    """
    if not filters:
        return "", []

    pieces: list[str] = []
    params: list[Any] = []

    # Each list-valued filter is bound as a single JSON parameter and
    # expanded at query time via SQLite's ``json_each``. This avoids
    # the ``IN (?, ?, ...)`` per-element bind expansion, which hits
    # SQLite's bind-variable limit (default 999, 32 766 on recent
    # builds) on large filters such as a derived view's full
    # entity_id list.
    for key in ("source_id", "entity_id", "source_kind"):
        if key not in filters:
            continue
        values = filters.get(key)
        if values is None:
            continue
        values_list = list(values)
        if not values_list:
            # Defensive: vector_search should have already short-circuited;
            # for direct callers of _build_filter_clause, signal "no match".
            return " WHERE 0 = 1", []
        pieces.append(f"{columns[key]} IN (SELECT value FROM json_each(?))")
        params.append(json.dumps(values_list))

    types_values = filters.get("entity_types")
    if types_values is not None:
        types_list = list(types_values)
        if not types_list:
            return " WHERE 0 = 1", []
        pieces.append(
            f"EXISTS (SELECT 1 FROM json_each({columns['entity_types']}) "
            "WHERE json_each.value IN (SELECT value FROM json_each(?)))"
        )
        params.append(json.dumps(types_list))

    if not pieces:
        return "", []
    return " WHERE " + " AND ".join(pieces), params


# ---------------------------------------------------------------------------
# Store — typed wrapper, the only thing that calls the SQL constants.
# ---------------------------------------------------------------------------


class Store:
    """SQLite-backed index store with a sqlite-vec vector table."""

    SCHEMA_VERSION = 2

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._conn: Any = None

    # --- Connection lifecycle ---

    def open(self) -> None:
        if self._conn is not None:
            return
        try:
            import sqlite_vec
        except ImportError:
            msg = (
                "sqlite-vec is required for the search index. "
                "Install it with: pip install crategraph[index]"
            )
            raise ImportError(msg) from None

        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = _connect(str(self.path))
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.execute("PRAGMA foreign_keys = ON")
        self._conn = conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Store:
        self.open()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @property
    def conn(self) -> Any:
        if self._conn is None:
            msg = "Store is not open — call .open() first."
            raise RuntimeError(msg)
        return self._conn

    # --- Schema + manifest ---

    def initialise(self, manifest: StoreManifest) -> None:
        """Create tables and write the manifest. Idempotent on re-open."""
        with self.conn:
            self.conn.executescript(_SQL_SCHEMA)
            self.conn.execute(_SQL_CREATE_VEC_TABLE.format(dim=manifest.embedding_dim))
            self._write_manifest(manifest)

    def _write_manifest(self, manifest: StoreManifest) -> None:
        self.conn.execute(_SQL_UPSERT_MANIFEST, ("manifest", manifest.to_json()))
        self.conn.execute(_SQL_UPSERT_MANIFEST, ("schema_version", str(self.SCHEMA_VERSION)))

    def read_manifest(self) -> StoreManifest | None:
        """Return the stored manifest, or None if the schema isn't built yet."""
        has_table = self.conn.execute(_SQL_HAS_MANIFEST_TABLE).fetchone()
        if not has_table:
            return None
        row = self.conn.execute(_SQL_GET_MANIFEST, ("manifest",)).fetchone()
        if row is None:
            return None
        return StoreManifest.from_json(row["value"])

    # --- Source-level operations ---

    def get_source_record(self, source_id: str) -> SourceRecord | None:
        row = self.conn.execute(_SQL_GET_SOURCE, (source_id,)).fetchone()
        if row is None:
            return None
        return SourceRecord(
            source_id=row["source_id"],
            source_path=row["source_path"],
            content_hash=row["content_hash"],
            entity_count=row["entity_count"],
            chunk_count=row["chunk_count"],
            indexed_at=row["indexed_at"],
        )

    def list_source_ids(self) -> list[str]:
        rows = self.conn.execute(_SQL_LIST_SOURCE_IDS).fetchall()
        return [r["source_id"] for r in rows]

    def delete_source(self, source_id: str) -> None:
        """Remove a source and all its text units / chunks / embeddings."""
        with self.conn:
            self.conn.execute(_SQL_DELETE_VEC_FOR_SOURCE, (source_id,))
            self.conn.execute(_SQL_DELETE_CHUNKS_FOR_SOURCE, (source_id,))
            self.conn.execute(_SQL_DELETE_TEXT_UNITS_FOR_SOURCE, (source_id,))
            self.conn.execute(_SQL_DELETE_SOURCE, (source_id,))

    def replace_source(
        self,
        text_units: Sequence[TextUnitSpec],
        embeddings: np.ndarray,
        *,
        source_id: str,
        source_path: str | None,
        content_hash: str,
        entity_count: int,
    ) -> None:
        """Atomically replace any existing rows for *source_id* with new ones.

        Old vec_chunks/chunks/text_units/sources rows for this source id
        are deleted and the new ones inserted in a single transaction,
        so a failed rebuild leaves the previous index intact.

        ``embeddings`` is a flat ``(N, embedding_dim)`` array where
        ``N == sum(len(u.chunks) for u in text_units)``. Embeddings are
        consumed in iteration order: each text unit's chunks first,
        then the next text unit.
        """
        total_chunks = sum(len(u.chunks) for u in text_units)
        if total_chunks != len(embeddings):
            msg = (
                f"chunks/embeddings length mismatch: "
                f"{total_chunks} chunk(s) declared across text_units, "
                f"{len(embeddings)} embedding row(s) provided"
            )
            raise ValueError(msg)

        indexed_at = datetime.now(UTC).isoformat()
        with self.conn:
            self.conn.execute(_SQL_DELETE_VEC_FOR_SOURCE, (source_id,))
            self.conn.execute(_SQL_DELETE_CHUNKS_FOR_SOURCE, (source_id,))
            self.conn.execute(_SQL_DELETE_TEXT_UNITS_FOR_SOURCE, (source_id,))
            self.conn.execute(
                _SQL_UPSERT_SOURCE,
                (
                    source_id,
                    source_path,
                    content_hash,
                    entity_count,
                    total_chunks,
                    indexed_at,
                ),
            )
            emb_idx = 0
            for unit in text_units:
                cursor = self.conn.execute(
                    _SQL_INSERT_TEXT_UNIT,
                    (
                        unit.source_id,
                        unit.entity_id,
                        json.dumps(list(unit.entity_types)),
                        unit.source_kind,
                        unit.text,
                        unit.token_count,
                    ),
                )
                text_unit_id = cursor.lastrowid
                for spec in unit.chunks:
                    chunk_cursor = self.conn.execute(
                        _SQL_INSERT_CHUNK,
                        (
                            text_unit_id,
                            unit.source_id,
                            spec.chunk_index,
                            spec.char_start,
                            spec.char_end,
                            spec.token_count,
                        ),
                    )
                    chunk_id = chunk_cursor.lastrowid
                    self.conn.execute(
                        _SQL_INSERT_VEC,
                        (chunk_id, embeddings[emb_idx].astype("float32").tobytes()),
                    )
                    emb_idx += 1

    # --- Search ---

    def vector_search(
        self,
        embedding: np.ndarray,
        *,
        k: int,
        filters: Mapping[str, Sequence[str]] | None = None,
        over_fetch: int = 5,
    ) -> list[SearchHit]:
        """Run a KNN search with optional metadata filters.

        When no filters are passed the KNN is asked for exactly ``k``
        rows. With filters, candidates are over-fetched (``k *
        over_fetch`` initially) and post-filtered; if that yields
        fewer than ``k`` matches, the fetch window is doubled and the
        query rerun until either ``k`` filtered hits are found or the
        index is exhausted. ``fetch_k`` strictly grows toward the total
        chunk count, so the loop is naturally bounded.
        """
        embedding_bytes = embedding.astype("float32").tobytes()
        normalised = self._normalise_filters(filters, allow_short_circuit=True)
        if normalised is None:
            return []
        has_filters = bool(normalised)

        if not has_filters:
            return self._run_knn(embedding_bytes, fetch_k=k, k_limit=k, filters=None)

        total = self._chunk_count()
        if total == 0:
            return []

        fetch_k = min(max(k * over_fetch, k), total)
        hits: list[SearchHit] = []
        while True:
            hits = self._run_knn(embedding_bytes, fetch_k=fetch_k, k_limit=k, filters=normalised)
            if len(hits) >= k or fetch_k >= total:
                return hits
            fetch_k = min(fetch_k * 2, total)

    def _normalise_filters(
        self,
        filters: Mapping[str, Sequence[str]] | None,
        *,
        allow_short_circuit: bool,
    ) -> dict[str, list[str]] | None:
        """Validate filter keys and return a list-of-strings dict.

        Returns ``None`` if ``allow_short_circuit`` and any value is an
        explicit empty sequence (caller meant "match nothing"); otherwise
        empty values are dropped.
        """
        normalised: dict[str, list[str]] = {}
        if not filters:
            return normalised
        for key, value in filters.items():
            if key not in _FILTER_KEYS_SUPPORTED:
                msg = (
                    f"Unsupported filter key {key!r}. Supported: {sorted(_FILTER_KEYS_SUPPORTED)}"
                )
                raise ValueError(msg)
            if value is None:
                continue
            value_list = list(value)
            if not value_list:
                if allow_short_circuit:
                    return None
                continue
            normalised[key] = value_list
        return normalised

    def _chunk_count(self) -> int:
        row = self.conn.execute(_SQL_COUNT_CHUNKS).fetchone()
        return int(row[0]) if row is not None else 0

    def _run_knn(
        self,
        embedding_bytes: bytes,
        *,
        fetch_k: int,
        k_limit: int,
        filters: Mapping[str, Sequence[str]] | None,
    ) -> list[SearchHit]:
        """Run a single KNN+filter+limit query and return the hits."""
        filter_sql, filter_params = _build_filter_clause(filters, _FILTER_COLUMNS_VECTOR_SEARCH)
        sql = _SQL_VECTOR_SEARCH_TEMPLATE.format(filter_sql=filter_sql)
        params: list[Any] = [embedding_bytes, fetch_k, *filter_params, k_limit]

        rows = self.conn.execute(sql, params).fetchall()
        return [_row_to_hit(row) for row in rows]

    # --- Iteration helpers (cached reads of text_units / chunks) ---

    def iter_source_records(self) -> Iterable[SourceRecord]:
        """Yield every recorded source. Used for manifest mismatch checks."""
        rows = self.conn.execute(_SQL_LIST_SOURCE_IDS).fetchall()
        for row in rows:
            sid = row["source_id"]
            record = self.get_source_record(sid)
            if record is not None:
                yield record

    def iter_text_records(
        self, *, filters: Mapping[str, Sequence[str]] | None = None
    ) -> Iterator[dict[str, Any]]:
        """Yield one dict per text unit, optionally filtered.

        Streaming: SQLite cursors yield rows one at a time, so peak
        memory is roughly one record's text.
        """
        normalised = self._normalise_filters(filters, allow_short_circuit=True)
        if normalised is None:
            return
        filter_sql, filter_params = _build_filter_clause(normalised, _FILTER_COLUMNS_TEXT_UNITS)
        sql = _SQL_ITER_TEXT_RECORDS_TEMPLATE.format(filter_sql=filter_sql)
        cursor = self.conn.execute(sql, filter_params)
        for row in cursor:
            yield {
                "source_id": row["source_id"],
                "entity_id": row["entity_id"],
                "entity_types": tuple(json.loads(row["entity_types"])),
                "source_kind": row["source_kind"],
                "text": row["text"],
                "token_count": row["token_count"],
            }

    def iter_chunk_records(
        self, *, filters: Mapping[str, Sequence[str]] | None = None
    ) -> Iterator[dict[str, Any]]:
        """Yield one dict per chunk with text reconstructed via SUBSTR.

        Streaming. Order is stable: by source_id, entity_id,
        source_kind, chunk_index.
        """
        normalised = self._normalise_filters(filters, allow_short_circuit=True)
        if normalised is None:
            return
        filter_sql, filter_params = _build_filter_clause(normalised, _FILTER_COLUMNS_CHUNKS)
        sql = _SQL_ITER_CHUNK_RECORDS_TEMPLATE.format(filter_sql=filter_sql)
        cursor = self.conn.execute(sql, filter_params)
        for row in cursor:
            yield {
                "source_id": row["source_id"],
                "entity_id": row["entity_id"],
                "entity_types": tuple(json.loads(row["entity_types"])),
                "source_kind": row["source_kind"],
                "chunk_index": row["chunk_index"],
                "char_start": row["char_start"],
                "char_end": row["char_end"],
                "token_count": row["token_count"],
                "text": row["text"],
            }


def _row_to_hit(row: Any) -> SearchHit:
    types = tuple(json.loads(row["entity_types"]))
    distance = float(row["distance"])
    score = 1.0 / (1.0 + distance)
    return SearchHit(
        source_id=row["source_id"],
        entity_id=row["entity_id"],
        entity_types=types,
        source_kind=row["source_kind"],
        chunk_index=row["chunk_index"],
        score=score,
        text=row["text"],
        char_start=row["char_start"],
        char_end=row["char_end"],
        token_count=row["token_count"],
    )
