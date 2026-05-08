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


def test_offsets_reconstruct_chunk_text_short(chunker: Chunker) -> None:
    """For a short text fitting in one chunk, offsets cover the whole input."""
    text = "Short input that fits in a single chunk."
    slices = list(chunker.chunk(text))
    assert len(slices) == 1
    s = slices[0]
    assert s.char_start == 0
    assert s.char_end == len(text)
    assert text[s.char_start : s.char_end] == s.text


def test_offsets_reconstruct_chunk_text_long(chunker: Chunker) -> None:
    """Each long-text chunk's offsets must reconstruct its text exactly."""
    text = " ".join(f"word{i}" for i in range(200))
    slices = list(chunker.chunk(text))
    assert len(slices) > 1
    for s in slices:
        assert text[s.char_start : s.char_end] == s.text, (
            f"offsets {s.char_start}:{s.char_end} don't reconstruct chunk"
        )


def test_offsets_align_with_sqlite_substr_for_non_ascii(chunker: Chunker) -> None:
    """Python slicing and SQLite SUBSTR must agree for non-ASCII text.

    Python's ``str`` is code-point indexed; SQLite's ``SUBSTR`` on TEXT
    columns is also code-point indexed (it counts characters, not UTF-8
    bytes). This test confirms the two stay aligned for emoji, combining
    marks, and CJK — which is the contract the indexer relies on when
    storing offsets and reconstructing via SUBSTR at query time.
    """
    pytest.importorskip("sqlite_vec")
    import sqlite3

    samples = [
        "café résumé naïve façade — coöperate",  # combining marks / accents
        "🐍 Python with emoji 🚀 deployed 🌍 worldwide",  # astral plane
        "東京から大阪まで新幹線で2時間半 " * 5,  # CJK, long enough to chunk
        "a✓b✗c ́̂ \U0001f600",  # mixed scripts + marks
    ]

    conn = sqlite3.connect(":memory:")
    try:
        for text in samples:
            slices = list(chunker.chunk(text))
            assert slices, f"no chunks emitted for {text!r}"
            for s in slices:
                py_slice = text[s.char_start : s.char_end]
                # SQLite SUBSTR is 1-indexed; length is end - start.
                row = conn.execute(
                    "SELECT SUBSTR(?, ?, ?)",
                    (text, s.char_start + 1, s.char_end - s.char_start),
                ).fetchone()
                sql_slice = row[0]
                assert py_slice == sql_slice, (
                    f"mismatch for {text!r} at offsets "
                    f"{s.char_start}:{s.char_end}\n"
                    f"  python: {py_slice!r}\n"
                    f"  sqlite: {sql_slice!r}"
                )
                assert s.text == py_slice
    finally:
        conn.close()
