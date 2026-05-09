"""Indexer — orchestrates extraction, chunking, embedding, and persistence.

The indexer consumes ``Graph.text_records()`` (the reader-agnostic core
text extractor) and adds the index-specific concerns: chunking,
embedding, manifest validation, and per-source content hashing for
incremental rebuilds.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from crategraph.core.graph import Graph
from crategraph.core.text import DEFAULT_TEXT_PROPERTIES
from crategraph.index.chunker import Chunker
from crategraph.index.hashing import (
    compute_source_hash,
    entities_by_source,
    source_path,
)
from crategraph.index.models import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_TOKENS,
    DEFAULT_MODEL,
    ChunkSpec,
    IndexerConfig,
    IndexerStats,
    TextUnitSpec,
)
from crategraph.index.store import Store, StoreManifest

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

PACKAGE_VERSION = "0.1.0"


class Indexer:
    """Build (or incrementally update) an index from a Graph.

    Args:
        graph: The graph to index. Single-source or multi-source via
            ``Crate(*paths)`` (or whichever reader produced the graph).
        store_path: Path to the SQLite index file. Created if missing.
        model: fastembed model id. Defaults to a small bge model.
        chunk_tokens: Target tokens per chunk.
        chunk_overlap: Token overlap between adjacent chunks.
        text_properties: Property allowlist for property-text records.
        batch_size: Embedding batch size.
        progress: If True, show a tqdm progress bar.
    """

    def __init__(
        self,
        graph: Graph,
        store_path: str | Path,
        *,
        model: str = DEFAULT_MODEL,
        chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        text_properties: Sequence[str] = DEFAULT_TEXT_PROPERTIES,
        batch_size: int = 64,
        progress: bool = True,
    ) -> None:
        self.graph = graph
        self.store_path = Path(store_path)
        self.config = IndexerConfig(
            model=model,
            chunk_tokens=chunk_tokens,
            chunk_overlap=chunk_overlap,
            text_properties=tuple(text_properties),
        )
        self.batch_size = batch_size
        self.progress = progress
        self._embedder = None

    # --- Public API ---

    def build(self) -> IndexerStats:
        """Index the graph, reusing existing work where possible.

        Returns a stats object describing what was done.
        """
        stats = IndexerStats()
        chunker = Chunker(
            model=self.config.model,
            chunk_tokens=self.config.chunk_tokens,
            chunk_overlap=self.config.chunk_overlap,
        )

        # Plan work before opening the embedder — cheap, no model load.
        per_source = entities_by_source(self.graph)
        per_source_hashes = {
            source_id: compute_source_hash(self.graph, ents, self.config)
            for source_id, ents in per_source.items()
        }

        with Store(self.store_path) as store:
            existing_manifest = store.read_manifest()
            self._validate_or_init(store, existing_manifest)

            # Decide work: new/changed/unchanged/removed.
            existing_source_ids = set(store.list_source_ids())
            current_source_ids = set(per_source.keys())

            for sid in existing_source_ids - current_source_ids:
                store.delete_source(sid)
                stats.sources_removed.append(sid)

            for source_id, entities in per_source.items():
                expected_hash = per_source_hashes[source_id]
                existing = store.get_source_record(source_id)
                if existing is not None and existing.content_hash == expected_hash:
                    stats.sources_skipped.append(source_id)
                    stats.total_entities += existing.entity_count
                    stats.total_chunks += existing.chunk_count
                    continue

                # Build replacement text units + chunk specs + embeddings
                # before touching the existing index, so a failure here
                # leaves the previous state intact. Store.replace_source
                # replaces atomically.
                text_units, chunk_texts = self._build_text_units(chunker, source_id)
                if not text_units:
                    # Source still has entities but produces no text (e.g.
                    # text_properties allowlist excludes everything, files
                    # all unsupported). If we previously indexed this
                    # source, drop its stale rows; otherwise just skip.
                    if existing is not None:
                        store.delete_source(source_id)
                        stats.sources_removed.append(source_id)
                        logger.info(
                            "Source %r now produces no chunks; removed stale rows",
                            source_id,
                        )
                    else:
                        logger.info("Source %r yielded no chunks; skipping", source_id)
                    continue

                embeddings = self._embed(chunk_texts)
                store.replace_source(
                    text_units,
                    embeddings,
                    source_id=source_id,
                    source_path=source_path(self.graph, entities),
                    content_hash=expected_hash,
                    entity_count=len(entities),
                )
                stats.sources_indexed.append(source_id)
                stats.total_entities += len(entities)
                stats.total_chunks += len(chunk_texts)

        return stats

    # --- Internals ---

    def _build_text_units(
        self, chunker: Chunker, source_id: str
    ) -> tuple[list[TextUnitSpec], list[str]]:
        """Materialise text units + flat chunk-text list for one source.

        Returns ``(units, chunk_texts)`` where ``chunk_texts`` is the
        flat embed-input list in the same order the store will consume.
        Text units yielding no chunks are skipped.
        """
        units: list[TextUnitSpec] = []
        chunk_texts: list[str] = []
        records = self.graph.text_records(
            text_properties=self.config.text_properties,
            filters={"source_id": [source_id]},
        )
        for record in records:
            slices = list(chunker.chunk(record["text"]))
            if not slices:
                continue
            specs = tuple(
                ChunkSpec(
                    chunk_index=idx,
                    char_start=s.char_start,
                    char_end=s.char_end,
                    token_count=s.token_count,
                )
                for idx, s in enumerate(slices)
            )
            # Re-tokenise the unit text rather than summing per-chunk
            # counts: with overlap, sums double-count the boundary
            # tokens and inflate the reported figure.
            unit_token_count = chunker.count_tokens(record["text"])
            units.append(
                TextUnitSpec(
                    source_id=record["source_id"],
                    entity_id=record["entity_id"],
                    entity_types=record["entity_types"],
                    source_kind=record["source_kind"],
                    text=record["text"],
                    token_count=unit_token_count,
                    chunks=specs,
                )
            )
            chunk_texts.extend(s.text for s in slices)
        return units, chunk_texts

    def _validate_or_init(self, store: Store, existing: StoreManifest | None) -> None:
        """Either confirm config compatibility or create a fresh schema."""
        if existing is not None:
            if existing.config != self.config:
                msg = (
                    f"Index at {self.store_path} was built with a different "
                    "configuration:\n"
                    f"  stored: {existing.config}\n"
                    f"  requested: {self.config}\n"
                    "Delete the index file and rebuild, or pass the "
                    "matching config."
                )
                raise ValueError(msg)
            return

        # Fresh index — probe embedding dimension, then create schema.
        dim = self._probe_embedding_dim()
        manifest = StoreManifest(
            config=self.config,
            embedding_dim=dim,
            package_version=PACKAGE_VERSION,
            created_at=datetime.now(UTC).isoformat(),
        )
        store.initialise(manifest)

    def _load_embedder(self):
        if self._embedder is not None:
            return self._embedder
        try:
            from fastembed import TextEmbedding
        except ImportError:
            msg = (
                "fastembed is required for indexing. "
                "Install it with: pip install crategraph[index]"
            )
            raise ImportError(msg) from None
        self._embedder = TextEmbedding(model_name=self.config.model)
        return self._embedder

    def _probe_embedding_dim(self) -> int:
        embedder = self._load_embedder()
        first = next(iter(embedder.embed(["probe"], batch_size=1)))
        return int(first.shape[0])

    def _embed(self, texts: list[str]) -> np.ndarray:
        import numpy as np

        embedder = self._load_embedder()
        gen: Any = embedder.embed(texts, batch_size=self.batch_size)
        if self.progress and len(texts) > 1:
            try:
                from tqdm import tqdm

                gen = tqdm(gen, total=len(texts), desc="Embedding chunks")
            except ImportError:
                pass
        return np.vstack(list(gen))
