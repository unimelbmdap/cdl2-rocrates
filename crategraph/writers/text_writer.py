"""Plain text writer — serialises Graph text records to one UTF-8 file."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from crategraph.core.interfaces import Writer

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from crategraph.core.graph import Graph


class TextWriter(Writer):
    """Write text extracted from a :class:`Graph` to a single file.

    The writer deliberately uses only the public ``graph.text_records()`` API.
    That keeps text export as a handoff view over text records rather than a
    second text-extraction implementation.
    """

    def can_write(self, path: str) -> bool:
        """Return True for plain text and Markdown file targets."""
        return path.lower().endswith((".txt", ".md"))

    def write(
        self,
        graph: Graph,
        path: str,
        *,
        overwrite: bool = False,
        source_kind: str = "file",
        store_path: str | Path | None = None,
        filters: Mapping[str, Any] | None = None,
        text_properties: Sequence[str] | None = None,
        restrict_to_view: bool = True,
        include_headers: bool = True,
        separator: str = "\n\n---\n\n",
        **kwargs: Any,
    ) -> None:
        """Serialise text records from *graph* to *path*.

        Args:
            graph: The graph whose text records should be exported.
            path: Target text or Markdown file.
            overwrite: Replace an existing file when ``True``.
            source_kind: ``"file"`` (default), ``"properties"``, or ``"all"``.
            store_path: Optional semantic-index store used by ``text_records``.
            filters: Optional filters forwarded to ``text_records``.
            text_properties: Optional property allowlist for live property text.
            restrict_to_view: Forwarded to ``text_records`` for cached reads.
            include_headers: Prefix each text unit with provenance comments.
            separator: Text inserted between records.
            **kwargs: Reserved for forward compatibility.
        """
        del kwargs

        target = Path(path)
        if target.exists() and not overwrite:
            raise FileExistsError(target)

        merged_filters = _merge_source_kind_filter(filters, source_kind)
        records = graph.text_records(
            store_path=store_path,
            text_properties=text_properties,
            filters=merged_filters,
            restrict_to_view=restrict_to_view,
        )

        wrote = False
        with target.open("w", encoding="utf-8") as f:
            for record in records:
                if wrote:
                    f.write(separator)
                f.write(_format_record(record, include_headers=include_headers))
                wrote = True
            if wrote:
                f.write("\n")


def _merge_source_kind_filter(
    filters: Mapping[str, Any] | None,
    source_kind: str,
) -> dict[str, Any] | None:
    """Return filters with the writer-level source_kind option applied."""
    if source_kind not in {"file", "properties", "all"}:
        msg = "source_kind must be 'file', 'properties', or 'all'."
        raise ValueError(msg)

    merged = dict(filters) if filters else {}
    if source_kind == "all":
        return merged or None

    if "source_kind" in merged:
        msg = "Pass source_kind as a writer argument, not inside filters."
        raise ValueError(msg)

    merged["source_kind"] = [source_kind]
    return merged


def _format_record(record: Mapping[str, Any], *, include_headers: bool) -> str:
    """Render one text record as a plain text block."""
    text = str(record.get("text", "")).rstrip("\n")
    if not include_headers:
        return text

    entity_types = record.get("entity_types", ())
    if isinstance(entity_types, str):
        rendered_types = entity_types
    else:
        rendered_types = ", ".join(str(value) for value in entity_types)

    headers = (
        f"# source_id: {_one_line(record.get('source_id', ''))}",
        f"# entity_id: {_one_line(record.get('entity_id', ''))}",
        f"# source_kind: {_one_line(record.get('source_kind', ''))}",
        f"# entity_types: {_one_line(rendered_types)}",
    )
    return "\n".join(headers) + "\n\n" + text


def _one_line(value: object) -> str:
    """Render metadata header values without embedded line breaks."""
    return " ".join(str(value).splitlines())


__all__ = ["TextWriter"]
