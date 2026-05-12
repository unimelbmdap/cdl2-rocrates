"""Tests for crategraph.writers.text_writer.TextWriter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from crategraph.writers.text_writer import TextWriter


class _TextRecordGraph:
    """Small fake graph exposing only the public text_records API."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records
        self.calls: list[dict[str, Any]] = []

    def text_records(
        self,
        *,
        store_path: str | Path | None = None,
        text_properties: list[str] | tuple[str, ...] | None = None,
        filters: dict[str, Any] | None = None,
        restrict_to_view: bool = True,
    ):
        self.calls.append(
            {
                "store_path": store_path,
                "text_properties": text_properties,
                "filters": filters,
                "restrict_to_view": restrict_to_view,
            }
        )
        yield from self.records


def _record(
    entity_id: str,
    text: str,
    *,
    source_kind: str = "file",
    entity_types: tuple[str, ...] = ("File",),
) -> dict[str, Any]:
    return {
        "source_id": "minimal-crate",
        "entity_id": entity_id,
        "entity_types": entity_types,
        "source_kind": source_kind,
        "text": text,
    }


def test_writes_single_text_file_with_headers(tmp_path: Path) -> None:
    graph = _TextRecordGraph(
        [
            _record("sample.txt", "First file text."),
            _record("notes.md", "Second file text."),
        ]
    )
    out = tmp_path / "corpus.txt"

    TextWriter().write(graph, str(out))

    assert out.read_text(encoding="utf-8") == (
        "# source_id: minimal-crate\n"
        "# entity_id: sample.txt\n"
        "# source_kind: file\n"
        "# entity_types: File\n\n"
        "First file text.\n\n"
        "---\n\n"
        "# source_id: minimal-crate\n"
        "# entity_id: notes.md\n"
        "# source_kind: file\n"
        "# entity_types: File\n\n"
        "Second file text.\n"
    )


def test_defaults_to_file_text_records(tmp_path: Path) -> None:
    graph = _TextRecordGraph([_record("sample.txt", "File text.")])

    TextWriter().write(graph, str(tmp_path / "corpus.txt"))

    assert graph.calls == [
        {
            "store_path": None,
            "text_properties": None,
            "filters": {"source_kind": ["file"]},
            "restrict_to_view": True,
        }
    ]


def test_source_kind_all_does_not_add_source_kind_filter(tmp_path: Path) -> None:
    graph = _TextRecordGraph([_record("#alice", "name: Alice", source_kind="properties")])

    TextWriter().write(graph, str(tmp_path / "corpus.txt"), source_kind="all")

    assert graph.calls[0]["filters"] is None


def test_forwards_text_records_options(tmp_path: Path) -> None:
    graph = _TextRecordGraph([_record("#alice", "name: Alice", source_kind="properties")])
    filters = {"entity_id": ["#alice"]}
    store = tmp_path / "index.db"

    TextWriter().write(
        graph,
        str(tmp_path / "corpus.md"),
        source_kind="properties",
        store_path=store,
        filters=filters,
        text_properties=["name", "description"],
        restrict_to_view=False,
    )

    assert graph.calls == [
        {
            "store_path": store,
            "text_properties": ["name", "description"],
            "filters": {"entity_id": ["#alice"], "source_kind": ["properties"]},
            "restrict_to_view": False,
        }
    ]


def test_can_write_text_and_markdown_paths() -> None:
    writer = TextWriter()

    assert writer.can_write("corpus.txt") is True
    assert writer.can_write("corpus.md") is True
    assert writer.can_write("CORPUS.TXT") is True
    assert writer.can_write("corpus.graphml") is False


def test_existing_file_requires_overwrite(tmp_path: Path) -> None:
    graph = _TextRecordGraph([_record("sample.txt", "Replacement text.")])
    out = tmp_path / "corpus.txt"
    out.write_text("Existing text.", encoding="utf-8")

    with pytest.raises(FileExistsError):
        TextWriter().write(graph, str(out))

    TextWriter().write(graph, str(out), overwrite=True)
    assert "Replacement text." in out.read_text(encoding="utf-8")


def test_rejects_source_kind_filter_and_source_kind_argument(tmp_path: Path) -> None:
    graph = _TextRecordGraph([_record("sample.txt", "File text.")])

    with pytest.raises(ValueError, match="source_kind"):
        TextWriter().write(
            graph,
            str(tmp_path / "corpus.txt"),
            source_kind="file",
            filters={"source_kind": ["properties"]},
        )


def test_get_writer_returns_text_writer() -> None:
    from crategraph.writers import get_writer

    assert get_writer("text") is TextWriter
    assert get_writer("txt") is TextWriter
