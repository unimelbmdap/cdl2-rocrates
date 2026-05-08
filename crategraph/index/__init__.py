"""Semantic indexing over RO-Crate (and other reader) graphs.

Gated by the ``[index]`` optional extra::

    pip install crategraph[index]

The extra pulls in ``fastembed`` (ONNX embeddings, no torch),
``sqlite-vec`` (single-file vector store), the ``[inspect]`` extra
(markitdown for file content extraction), plus ``tokenizers`` and
``tqdm``.

Two layers of API:

1. Sugar on ``Graph`` / ``Crate``::

       crate.build_semantic_index(store_path="search.db")
       hits = crate.semantic_search("query", store_path="search.db")

2. Explicit classes (this module)::

       from crategraph.index import Indexer, Searcher

       Indexer(crate, store_path="search.db").build()
       hits = Searcher("search.db").search("query")
"""

from __future__ import annotations

from crategraph.index.indexer import Indexer
from crategraph.index.models import (
    IndexerConfig,
    IndexerStats,
    SearchHit,
    SourceRecord,
)
from crategraph.index.searcher import Searcher

__all__ = [
    "Indexer",
    "IndexerConfig",
    "IndexerStats",
    "SearchHit",
    "Searcher",
    "SourceRecord",
]
