"""Shared dataclasses for the index subpackage."""

from __future__ import annotations

from dataclasses import dataclass, field

from crategraph.core.text import DEFAULT_TEXT_PROPERTIES, SourceKind

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_CHUNK_TOKENS = 300
DEFAULT_CHUNK_OVERLAP = 50


@dataclass(frozen=True)
class ChunkSpec:
    """A chunk's offsets within its parent text unit.

    Offsets are character positions in the canonical ``text_units.text``
    such that ``unit_text[char_start:char_end]`` reconstructs the chunk.
    """

    chunk_index: int
    char_start: int
    char_end: int
    token_count: int


@dataclass(frozen=True)
class TextUnitSpec:
    """A canonical text unit plus the chunk offsets the indexer will store.

    Used to communicate the indexer's output to the store. The store
    writes one ``text_units`` row plus one ``chunks`` row per
    :class:`ChunkSpec`, all atomically, and inserts the corresponding
    embeddings into ``vec_chunks``.
    """

    source_id: str
    entity_id: str
    entity_types: tuple[str, ...]
    source_kind: SourceKind
    text: str
    token_count: int
    chunks: tuple[ChunkSpec, ...]


@dataclass(frozen=True)
class SearchHit:
    """A single search result."""

    source_id: str
    entity_id: str
    entity_types: tuple[str, ...]
    source_kind: SourceKind
    chunk_index: int
    score: float
    text: str

    def __repr__(self) -> str:
        snippet = self.text.strip().replace("\n", " ")
        if len(snippet) > 80:
            snippet = snippet[:77] + "..."
        return f"SearchHit({self.score:.3f}, {self.entity_id!r}, {self.source_kind}, {snippet!r})"


@dataclass(frozen=True)
class IndexerConfig:
    """Configuration that must match between index build and search.

    Stored in the on-disk manifest; mismatches refuse to load.
    """

    model: str = DEFAULT_MODEL
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    text_properties: tuple[str, ...] = DEFAULT_TEXT_PROPERTIES

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "chunk_tokens": self.chunk_tokens,
            "chunk_overlap": self.chunk_overlap,
            "text_properties": list(self.text_properties),
        }

    @classmethod
    def from_dict(cls, data: dict) -> IndexerConfig:
        return cls(
            model=data["model"],
            chunk_tokens=data["chunk_tokens"],
            chunk_overlap=data["chunk_overlap"],
            text_properties=tuple(data.get("text_properties", DEFAULT_TEXT_PROPERTIES)),
        )


@dataclass(frozen=True)
class SourceRecord:
    """Per-source manifest entry tracking what's indexed."""

    source_id: str
    source_path: str | None
    content_hash: str
    entity_count: int
    chunk_count: int
    indexed_at: str

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "source_path": self.source_path,
            "content_hash": self.content_hash,
            "entity_count": self.entity_count,
            "chunk_count": self.chunk_count,
            "indexed_at": self.indexed_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SourceRecord:
        return cls(
            source_id=data["source_id"],
            source_path=data.get("source_path"),
            content_hash=data["content_hash"],
            entity_count=data["entity_count"],
            chunk_count=data["chunk_count"],
            indexed_at=data["indexed_at"],
        )


@dataclass
class IndexerStats:
    """Build report — what changed and what didn't."""

    sources_indexed: list[str] = field(default_factory=list)
    sources_skipped: list[str] = field(default_factory=list)
    sources_removed: list[str] = field(default_factory=list)
    total_chunks: int = 0
    total_entities: int = 0
