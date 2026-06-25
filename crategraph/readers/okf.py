"""Open Knowledge Format reader.

Loads an OKF knowledge bundle from Markdown concept documents. Requires
``PyYAML`` and ``markdown-it-py`` (install via ``pip install crategraph[okf]``).
"""

from __future__ import annotations

import posixpath
import warnings
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

from crategraph.core.graph import Graph
from crategraph.core.interfaces import Reader
from crategraph.core.models import Entity, Relationship

_RESERVED_FILENAMES = {"index.md", "log.md"}
_RELATIONSHIP_TYPE = "linksTo"


def _require_okf() -> tuple[Any, Any]:
    """Import the optional OKF dependencies with a useful error message."""
    try:
        import yaml
        from markdown_it import MarkdownIt
    except ImportError:
        msg = "OKFReader requires the [okf] extra. Install it with: pip install crategraph[okf]"
        raise ImportError(msg) from None
    return yaml, MarkdownIt


class OKFReader(Reader):
    """Read an Open Knowledge Format directory into a :class:`Graph`.

    Concept IDs are bundle-relative Markdown paths without the ``.md``
    suffix. Frontmatter ``type`` values become entity types, Markdown
    bodies are stored in the ``text`` property, and links between concept
    documents become directed ``linksTo`` relationships.

    Loading is permissive: malformed concept documents and broken links
    produce aggregate warnings and counters in ``Graph.metadata``.

    When combining readers in a :class:`~crategraph.core.corpus.Corpus`,
    place ``OKFReader`` before ``SimpleFolderReader`` because plain OKF
    bundles have no mandatory manifest and also look like ordinary folders.
    """

    def can_read(self, path: str) -> bool:
        """Return whether *path* looks like a conforming OKF bundle.

        OKF has no mandatory manifest. Detection is therefore conservative:
        the directory must contain at least one non-reserved Markdown
        document, and every such document must have parseable YAML
        frontmatter with a non-empty scalar ``type``.
        """
        root = Path(path)
        if not root.is_dir() or (root / "ro-crate-metadata.json").is_file():
            return False

        try:
            documents = self._concept_paths(root)
        except OSError:
            return False
        if not documents:
            return False

        for document in documents:
            try:
                frontmatter, _ = self._parse_document(document)
            except (OSError, ValueError):
                return False
            if self._normalise_type(frontmatter.get("type")) is None:
                return False
        return True

    def read(self, path: str) -> Graph:
        """Read the OKF bundle at *path* and return a populated graph."""
        root = Path(path).resolve()
        if not root.exists():
            msg = f"Path does not exist: {path}"
            raise FileNotFoundError(msg)
        if not root.is_dir():
            msg = f"Path is not a directory: {path}"
            raise NotADirectoryError(msg)

        metadata = self._read_bundle_metadata(root)
        metadata["format"] = "okf"
        graph = Graph(source=str(root), metadata=metadata)

        parsed: dict[str, tuple[str, list[tuple[str, str]]]] = {}
        document_to_id: dict[str, str] = {}
        skipped: list[str] = []

        # First pass: parse every valid concept and create all entities.
        for document in self._concept_paths(root):
            relative_path = document.relative_to(root).as_posix()
            concept_id = relative_path.removesuffix(".md")
            try:
                frontmatter, body = self._parse_document(document)
            except (OSError, ValueError) as exc:
                skipped.append(f"{relative_path}: {exc}")
                continue

            concept_type = self._normalise_type(frontmatter.get("type"))
            if concept_type is None:
                skipped.append(f"{relative_path}: missing non-empty string 'type'")
                continue

            links = self._extract_markdown_links(body)
            external_links = [href for href, _label in links if self._is_external_link(href)]

            properties = {key: value for key, value in frontmatter.items() if key != "type"}
            title = properties.get("title")
            name = properties.get("name")
            if isinstance(title, str) and title.strip():
                display_name = title.strip()
            elif isinstance(name, str) and name.strip():
                display_name = name.strip()
            else:
                display_name = PurePosixPath(concept_id).name
            properties["name"] = display_name
            properties["text"] = body
            properties["document_path"] = relative_path
            if external_links:
                properties["external_links"] = external_links

            graph._add_node(
                Entity(
                    id=concept_id,
                    types=(concept_type,),
                    properties=properties,
                    source=str(root),
                )
            )
            parsed[concept_id] = (relative_path, links)
            document_to_id[relative_path] = concept_id

        # Second pass: resolve links now that every valid target is known.
        broken: list[str] = []
        for source_id, (source_document, links) in parsed.items():
            for href, label in links:
                target_document = self._resolve_target_document(
                    href,
                    source_document=source_document,
                )
                if target_document is None:
                    continue
                target_id = document_to_id.get(target_document)
                if target_id is None:
                    broken.append(f"{source_document} -> {href}")
                    continue
                graph._add_edge(
                    Relationship(
                        source=source_id,
                        target=target_id,
                        type=_RELATIONSHIP_TYPE,
                        properties={
                            "label": label,
                            "href": href,
                        },
                    )
                )

        if skipped:
            graph.metadata["skipped_document_count"] = len(skipped)
            self._warn_aggregate("Skipped OKF concept document(s)", skipped)
        if broken:
            graph.metadata["broken_link_count"] = len(broken)
            self._warn_aggregate("Ignored broken OKF concept link(s)", broken)

        return graph

    # --- Bundle discovery and parsing ---

    def _concept_paths(self, root: Path) -> list[Path]:
        """Return deterministic, non-reserved, non-symlink concept paths."""
        documents: list[Path] = []
        for path in root.rglob("*.md"):
            if path.name.lower() in _RESERVED_FILENAMES:
                continue
            if not path.is_file() or self._contains_symlink(path, root):
                continue
            documents.append(path)
        return sorted(documents, key=lambda item: item.relative_to(root).as_posix())

    @staticmethod
    def _contains_symlink(path: Path, root: Path) -> bool:
        """Return whether *path* or one of its bundle-relative parents is a symlink."""
        current = path
        while current != root:
            if current.is_symlink():
                return True
            current = current.parent
        return False

    def _parse_document(self, path: Path) -> tuple[dict[str, Any], str]:
        """Parse YAML frontmatter and return it with the Markdown body."""
        yaml, _ = _require_okf()
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        if not lines or lines[0].strip() != "---":
            raise ValueError("missing YAML frontmatter")

        closing = next(
            (
                index
                for index, line in enumerate(lines[1:], start=1)
                if line.strip() in {"---", "..."}
            ),
            None,
        )
        if closing is None:
            raise ValueError("unterminated YAML frontmatter")

        try:
            loaded = yaml.safe_load("".join(lines[1:closing]))
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid YAML frontmatter: {exc}") from exc
        if loaded is None:
            frontmatter: dict[str, Any] = {}
        elif isinstance(loaded, dict):
            frontmatter = loaded
        else:
            raise ValueError("YAML frontmatter must be a mapping")
        return frontmatter, "".join(lines[closing + 1 :])

    def _read_bundle_metadata(self, root: Path) -> dict[str, Any]:
        """Read optional bundle metadata from the root ``index.md``."""
        index = root / "index.md"
        if not index.is_file() or index.is_symlink():
            return {}
        try:
            frontmatter, body = self._parse_document(index)
        except (OSError, ValueError) as exc:
            warnings.warn(f"Ignored invalid OKF index.md: {exc}", stacklevel=2)
            return {}
        metadata = dict(frontmatter)
        if body.strip():
            metadata["text"] = body
        return metadata

    @staticmethod
    def _normalise_type(value: Any) -> str | None:
        """Return a stripped scalar concept type, or ``None``."""
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped or None

    # --- Markdown links ---

    def _extract_markdown_links(self, body: str) -> list[tuple[str, str]]:
        """Return ``(href, label)`` pairs for Markdown links in source order."""
        _, markdown_it_class = _require_okf()
        tokens = markdown_it_class("commonmark").parse(body)
        links: list[tuple[str, str]] = []

        for token in tokens:
            children = token.children or []
            href: str | None = None
            label_parts: list[str] = []
            for child in children:
                if child.type == "link_open":
                    href = child.attrGet("href")
                    label_parts = []
                elif child.type == "link_close" and href is not None:
                    links.append((href, "".join(label_parts).strip()))
                    href = None
                    label_parts = []
                elif href is not None and child.type in {"text", "code_inline"}:
                    label_parts.append(child.content)
        return links

    @staticmethod
    def _is_external_link(href: str) -> bool:
        """Return whether *href* refers outside the OKF bundle."""
        parts = urlsplit(href)
        return bool(parts.scheme or parts.netloc)

    def _resolve_target_document(
        self,
        href: str,
        *,
        source_document: str,
    ) -> str | None:
        """Resolve an internal link to a safe bundle-relative Markdown path."""
        parts = urlsplit(href)
        if parts.scheme or parts.netloc or not parts.path:
            return None

        decoded = unquote(parts.path).replace("\\", "/")
        if "\x00" in decoded:
            return None

        if decoded.startswith("/"):
            candidate = decoded.lstrip("/")
        else:
            candidate = posixpath.join(posixpath.dirname(source_document), decoded)
        normalised = posixpath.normpath(candidate)

        if normalised in {"", ".", ".."} or normalised.startswith("../"):
            return None
        if normalised.endswith("/"):
            normalised += "index.md"
        elif not PurePosixPath(normalised).suffix:
            normalised += ".md"
        if PurePosixPath(normalised).name.lower() in _RESERVED_FILENAMES:
            return None
        return normalised

    @staticmethod
    def _warn_aggregate(prefix: str, details: list[str]) -> None:
        """Emit one bounded warning for a group of recoverable issues."""
        preview = "; ".join(details[:3])
        if len(details) > 3:
            preview += f"; and {len(details) - 3} more"
        warnings.warn(f"{prefix} ({len(details)}): {preview}", stacklevel=3)
