"""Searcher — query an existing index.

Loads the embedding model named in the index's manifest (so the
runtime model always matches what was used at build time) and runs
KNN over the sqlite-vec store.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from crategraph.index.models import SearchHit
from crategraph.index.store import Store, StoreManifest

if TYPE_CHECKING:
    import numpy as np


class Searcher:
    """Query an on-disk index."""

    def __init__(self, store_path: str | Path) -> None:
        self.store_path = Path(store_path)
        if not self.store_path.exists():
            msg = f"No index file at {self.store_path}."
            raise FileNotFoundError(msg)
        self._embedder = None
        self._manifest: StoreManifest | None = None

    @property
    def manifest(self) -> StoreManifest:
        if self._manifest is None:
            with Store(self.store_path) as store:
                manifest = store.read_manifest()
            if manifest is None:
                msg = (
                    f"Index at {self.store_path} has no manifest — "
                    "it may be corrupt or built by an incompatible version."
                )
                raise ValueError(msg)
            self._manifest = manifest
        return self._manifest

    def search(
        self,
        query: str,
        *,
        k: int = 10,
        filters: Mapping[str, Sequence[str]] | None = None,
    ) -> list[SearchHit]:
        """Return the top *k* hits for *query*.

        ``filters`` keys (all optional, all "any-of" semantics):

        - ``source_id``: list[str] — restrict to these source ids
        - ``entity_id``: list[str] — restrict to these entities
        - ``entity_types``: list[str] — match if entity has any of these
        - ``source_kind``: list of ``"properties"`` or ``"file"``
        """
        manifest = self.manifest
        embedding = self._embed_query(query, model=manifest.config.model)
        with Store(self.store_path) as store:
            return store.vector_search(embedding, k=k, filters=filters)

    def known_source_ids(self) -> list[str]:
        """Return the source ids the index was built against."""
        with Store(self.store_path) as store:
            return store.list_source_ids()

    def _embed_query(self, query: str, *, model: str) -> np.ndarray:
        try:
            from fastembed import TextEmbedding
        except ImportError:
            msg = (
                "fastembed is required for searching. "
                "Install it with: pip install crategraph[index]"
            )
            raise ImportError(msg) from None

        if self._embedder is None:
            self._embedder = TextEmbedding(model_name=model)
        if hasattr(self._embedder, "query_embed"):
            arr = next(iter(self._embedder.query_embed([query])))
        else:
            arr = next(iter(self._embedder.embed([query])))
        return arr
