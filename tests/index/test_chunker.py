"""Tests for crategraph.index.chunker."""

from __future__ import annotations

import pytest

pytest.importorskip("tokenizers")

from crategraph.index.chunker import Chunker
from crategraph.index.models import DEFAULT_MODEL


@pytest.fixture(scope="module")
def chunker() -> Chunker:
    return Chunker(model=DEFAULT_MODEL, chunk_tokens=20, chunk_overlap=5)


def test_empty_text_yields_nothing(chunker: Chunker) -> None:
    assert list(chunker.chunk("")) == []
    assert list(chunker.chunk("   \n  ")) == []


def test_short_text_yields_single_chunk(chunker: Chunker) -> None:
    text = "A short sentence."
    slices = list(chunker.chunk(text))
    assert len(slices) == 1
    assert slices[0].text == text
    assert slices[0].token_count > 0
    assert slices[0].token_count <= chunker.chunk_tokens


def test_long_text_yields_multiple_overlapping_chunks(chunker: Chunker) -> None:
    text = " ".join(f"word{i}" for i in range(200))
    slices = list(chunker.chunk(text))

    assert len(slices) > 1
    for slice_ in slices:
        assert slice_.token_count <= chunker.chunk_tokens
        assert slice_.text.strip()

    full_token_count = chunker.count_tokens(text)
    step = chunker.chunk_tokens - chunker.chunk_overlap
    expected_chunks = (full_token_count + step - 1) // step
    assert abs(len(slices) - expected_chunks) <= 1


def test_invalid_overlap_rejected() -> None:
    with pytest.raises(ValueError, match="chunk_overlap"):
        Chunker(model=DEFAULT_MODEL, chunk_tokens=10, chunk_overlap=10)
    with pytest.raises(ValueError, match="chunk_overlap"):
        Chunker(model=DEFAULT_MODEL, chunk_tokens=10, chunk_overlap=15)


def test_chunks_cover_full_text(chunker: Chunker) -> None:
    """Each character of the input should appear in at least one chunk."""
    text = " ".join(f"distinct{i}" for i in range(100))
    slices = list(chunker.chunk(text))
    joined = "".join(s.text for s in slices)
    for i in range(100):
        token = f"distinct{i}"
        assert token in joined, f"missing {token} from chunked output"
