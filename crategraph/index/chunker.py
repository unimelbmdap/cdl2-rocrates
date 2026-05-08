"""Token-aware chunking with overlap.

Uses the embedding model's tokenizer (loaded via the ``tokenizers``
package) so chunk boundaries match how the model will see the text.
This is the same lesson as ``hansard-rag-mcp``: a tokenizer mismatch
between chunker and embedder produces silently truncated chunks at
inference time.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass


@dataclass
class TextSlice:
    """A slice of source text with its token count."""

    text: str
    token_count: int


class Chunker:
    """Slide a fixed-size window of tokens over text, emitting overlapping chunks.

    Boundaries snap to token offsets in the original string so the
    emitted text is verbatim — no whitespace loss from decode round-trips.
    """

    def __init__(
        self,
        model: str,
        chunk_tokens: int = 300,
        chunk_overlap: int = 50,
    ) -> None:
        if chunk_overlap >= chunk_tokens:
            msg = (
                f"chunk_overlap ({chunk_overlap}) must be smaller than "
                f"chunk_tokens ({chunk_tokens})."
            )
            raise ValueError(msg)
        self.model = model
        self.chunk_tokens = chunk_tokens
        self.chunk_overlap = chunk_overlap
        self._tokenizer = None

    def _load_tokenizer(self):
        if self._tokenizer is not None:
            return self._tokenizer
        try:
            from tokenizers import Tokenizer
        except ImportError:
            msg = (
                "tokenizers is required for chunking. "
                "Install it with: pip install crategraph[index]"
            )
            raise ImportError(msg) from None

        self._tokenizer = Tokenizer.from_pretrained(self.model)
        return self._tokenizer

    def chunk(self, text: str) -> Iterator[TextSlice]:
        """Yield overlapping chunks covering *text*.

        Empty/whitespace-only input yields nothing.
        """
        if not text or not text.strip():
            return

        tokenizer = self._load_tokenizer()
        encoding = tokenizer.encode(text, add_special_tokens=False)
        ids = encoding.ids
        offsets = encoding.offsets

        if not ids:
            return

        if len(ids) <= self.chunk_tokens:
            yield TextSlice(text=text, token_count=len(ids))
            return

        step = self.chunk_tokens - self.chunk_overlap
        start = 0
        n = len(ids)
        while start < n:
            end = min(start + self.chunk_tokens, n)
            char_start = offsets[start][0]
            char_end = offsets[end - 1][1]
            slice_text = text[char_start:char_end]
            yield TextSlice(text=slice_text, token_count=end - start)
            if end == n:
                break
            start += step

    def count_tokens(self, text: str) -> int:
        """Return the token count for *text* under this chunker's tokenizer."""
        if not text:
            return 0
        tokenizer = self._load_tokenizer()
        return len(tokenizer.encode(text, add_special_tokens=False).ids)
