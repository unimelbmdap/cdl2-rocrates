"""SQLite + sqlite-vec persistence for the index.

This module is the **sole owner of SQL** in the package. All SQL
strings live as named module-level ``_SQL_*`` constants below, and
public callers interact via typed methods on ``Store``. Other modules
(indexer, searcher, hashing, the graph delegations) must never embed
SQL — if a new query is needed, add a method here.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from crategraph.index.models import (
    Chunk,
    IndexerConfig,
    SearchHit,
    SourceRecord,
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
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    entity_types TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    token_count INTEGER NOT NULL,
    text TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(source_id)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chunks_source_entity
    ON chunks(source_id, entity_id);
"""

_SQL_CREATE_VEC_TABLE = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding float[{dim}])"
)

_SQL_UPSERT_MANIFEST = "INSERT OR REPLACE INTO manifest(key, value) VALUES (?, ?)"

_SQL_GET_MANIFEST = "SELECT value FROM manifest WHERE key = ?"

_SQL_HAS_MANIFEST_TABLE = "SELECT 1 FROM sqlite_master WHERE type='table' AND name='manifest'"

_SQL_GET_SOURCE = "SELECT * FROM sources WHERE source_id = ?"

_SQL_LIST_SOURCE_IDS = "SELECT source_id FROM sources ORDER BY source_id"

_SQL_DELETE_VEC_FOR_SOURCE = (
    "DELETE FROM vec_chunks WHERE rowid IN (SELECT chunk_id FROM chunks WHERE source_id = ?)"
)

_SQL_DELETE_CHUNKS_FOR_SOURCE = "DELETE FROM chunks WHERE source_id = ?"

_SQL_DELETE_SOURCE = "DELETE FROM sources WHERE source_id = ?"

_SQL_UPSERT_SOURCE = (
    "INSERT OR REPLACE INTO sources"
    "(source_id, source_path, content_hash, entity_count, chunk_count, indexed_at) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)

_SQL_INSERT_CHUNK = (
    "INSERT INTO chunks"
    "(source_id, entity_id, entity_types, source_kind, "
    "chunk_index, token_count, text) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)

_SQL_INSERT_VEC = "INSERT INTO vec_chunks(rowid, embedding) VALUES (?, ?)"

_SQL_COUNT_CHUNKS = "SELECT COUNT(*) FROM chunks"

# Vector search template — `{filter_sql}` is filled in safely by
# _build_filter_clause(), which only emits placeholders, never values.
_SQL_VECTOR_SEARCH_TEMPLATE = (
    "WITH knn AS ("
    "  SELECT rowid, distance "
    "  FROM vec_chunks "
    "  WHERE embedding MATCH ? AND k = ?"
    ") "
    "SELECT c.source_id, c.entity_id, c.entity_types, c.source_kind, "
    "  c.chunk_index, c.text, knn.distance "
    "FROM knn JOIN chunks c ON c.chunk_id = knn.rowid"
    "{filter_sql} "
    "ORDER BY knn.distance "
    "LIMIT ?"
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


def _build_filter_clause(
    filters: Mapping[str, Sequence[str]] | None,
) -> tuple[str, list[Any]]:
    """Return (sql_fragment, params) for the optional WHERE clause.

    Caller composes the fragment into the prepared template; values
    are returned as a separate parameter list so they're bound, not
    interpolated.
    """
    if not filters:
        return "", []

    pieces: list[str] = []
    params: list[Any] = []

    source_ids = filters.get("source_id")
    if source_ids:
        ids = list(source_ids)
        placeholders = ",".join("?" * len(ids))
        pieces.append(f"c.source_id IN ({placeholders})")
        params.extend(ids)

    entity_ids = filters.get("entity_id")
    if entity_ids:
        ids = list(entity_ids)
        placeholders = ",".join("?" * len(ids))
        pieces.append(f"c.entity_id IN ({placeholders})")
        params.extend(ids)

    source_kinds = filters.get("source_kind")
    if source_kinds:
        kinds = list(source_kinds)
        placeholders = ",".join("?" * len(kinds))
        pieces.append(f"c.source_kind IN ({placeholders})")
        params.extend(kinds)

    entity_types = filters.get("entity_types")
    if entity_types:
        types = list(entity_types)
        placeholders = ",".join("?" * len(types))
        pieces.append(
            f"EXISTS (SELECT 1 FROM json_each(c.entity_types) "
            f"WHERE json_each.value IN ({placeholders}))"
        )
        params.extend(types)

    if not pieces:
        return "", []
    return " WHERE " + " AND ".join(pieces), params


# ---------------------------------------------------------------------------
# Store — typed wrapper, the only thing that calls the SQL constants.
# ---------------------------------------------------------------------------


class Store:
    """SQLite-backed index store with a sqlite-vec vector table."""

    SCHEMA_VERSION = 1

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
        """Remove a source and all its chunks/embeddings."""
        with self.conn:
            self.conn.execute(_SQL_DELETE_VEC_FOR_SOURCE, (source_id,))
            self.conn.execute(_SQL_DELETE_CHUNKS_FOR_SOURCE, (source_id,))
            self.conn.execute(_SQL_DELETE_SOURCE, (source_id,))

    def replace_source(
        self,
        chunks: Sequence[Chunk],
        embeddings: np.ndarray,
        *,
        source_id: str,
        source_path: str | None,
        content_hash: str,
        entity_count: int,
    ) -> None:
        """Atomically replace any existing rows for *source_id* with new ones.

        Old vec_chunks/chunks/sources rows for this source id are deleted
        and the new ones inserted in a single transaction, so a failed
        rebuild leaves the previous index intact rather than wiping it.

        ``embeddings`` is shape ``(len(chunks), embedding_dim)``, ``np.float32``.
        """
        if len(chunks) != len(embeddings):
            msg = f"chunks/embeddings length mismatch: {len(chunks)} vs {len(embeddings)}"
            raise ValueError(msg)

        indexed_at = datetime.now(UTC).isoformat()
        with self.conn:
            self.conn.execute(_SQL_DELETE_VEC_FOR_SOURCE, (source_id,))
            self.conn.execute(_SQL_DELETE_CHUNKS_FOR_SOURCE, (source_id,))
            self.conn.execute(
                _SQL_UPSERT_SOURCE,
                (
                    source_id,
                    source_path,
                    content_hash,
                    entity_count,
                    len(chunks),
                    indexed_at,
                ),
            )
            for chunk, emb in zip(chunks, embeddings, strict=True):
                cursor = self.conn.execute(
                    _SQL_INSERT_CHUNK,
                    (
                        chunk.source_id,
                        chunk.entity_id,
                        json.dumps(list(chunk.entity_types)),
                        chunk.source_kind,
                        chunk.chunk_index,
                        chunk.token_count,
                        chunk.text,
                    ),
                )
                chunk_id = cursor.lastrowid
                self.conn.execute(_SQL_INSERT_VEC, (chunk_id, emb.astype("float32").tobytes()))

    # --- Search ---

    def vector_search(
        self,
        embedding: np.ndarray,
        *,
        k: int,
        filters: Mapping[str, Sequence[str]] | None = None,
        over_fetch: int = 5,
        max_iterations: int = 6,
    ) -> list[SearchHit]:
        """Run a KNN search with optional metadata filters.

        When no filters are passed the KNN is asked for exactly ``k``
        rows. With filters, candidates are over-fetched (``k *
        over_fetch`` initially) and post-filtered; if that yields
        fewer than ``k`` matches, the fetch window is doubled and the
        query rerun until either ``k`` filtered hits are found or the
        index is exhausted. ``max_iterations`` caps the doublings as a
        safety belt.
        """
        embedding_bytes = embedding.astype("float32").tobytes()
        # Normalise filter values, distinguishing ``None`` (no filter for
        # that key) from an explicit empty sequence (caller intends "no
        # matches"). An empty sequence short-circuits to no results
        # rather than silently dropping the constraint.
        normalised: dict[str, list[str]] = {}
        if filters:
            for key, value in filters.items():
                if key not in _FILTER_KEYS_SUPPORTED:
                    msg = (
                        f"Unsupported filter key {key!r}. "
                        f"Supported: {sorted(_FILTER_KEYS_SUPPORTED)}"
                    )
                    raise ValueError(msg)
                if value is None:
                    continue
                value_list = list(value)
                if not value_list:
                    return []
                normalised[key] = value_list
        has_filters = bool(normalised)

        if not has_filters:
            return self._run_knn(embedding_bytes, fetch_k=k, k_limit=k, filters=None)

        total = self._chunk_count()
        if total == 0:
            return []

        fetch_k = min(max(k * over_fetch, k), total)
        hits: list[SearchHit] = []
        for _ in range(max_iterations):
            hits = self._run_knn(embedding_bytes, fetch_k=fetch_k, k_limit=k, filters=normalised)
            if len(hits) >= k or fetch_k >= total:
                return hits
            fetch_k = min(fetch_k * 2, total)
        return hits

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
        filter_sql, filter_params = _build_filter_clause(filters)
        sql = _SQL_VECTOR_SEARCH_TEMPLATE.format(filter_sql=filter_sql)
        params: list[Any] = [embedding_bytes, fetch_k, *filter_params, k_limit]

        rows = self.conn.execute(sql, params).fetchall()
        return [_row_to_hit(row) for row in rows]

    # --- Iteration helpers (used by index/text_reader for cached reads) ---

    def iter_source_records(self) -> Iterable[SourceRecord]:
        """Yield every recorded source. Used for manifest mismatch checks."""
        rows = self.conn.execute(_SQL_LIST_SOURCE_IDS).fetchall()
        for row in rows:
            sid = row["source_id"]
            record = self.get_source_record(sid)
            if record is not None:
                yield record


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
    )
