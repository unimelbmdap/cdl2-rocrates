"""Simple folder reader — builds a structural Graph from any directory.

Deliberately minimal: infers ``Dataset`` and ``File`` entities and
``hasPart`` relationships from the filesystem tree.  Does *not* infer
authors, titles, timestamps, or any other semantic content.  Authoring
real RO-Crates remains the job of dedicated tools (Crate-O, ro-crate-py).

Defers to :class:`ROCrateReader` when ``ro-crate-metadata.json`` is
present — ``can_read`` returns ``False`` in that case so a ``Corpus``
with both readers routes authored crates correctly.
"""

from __future__ import annotations

import mimetypes
import warnings
from pathlib import Path

from crategraph.core.graph import Graph
from crategraph.core.interfaces import Reader
from crategraph.core.models import Entity, Relationship

_METADATA_FILENAME = "ro-crate-metadata.json"


class SimpleFolderReader(Reader):
    """Read a plain directory into a Graph.

    Args:
        skip_hidden: When ``True`` (default), drop entries whose name
            starts with ``"."`` (``.git/``, ``.DS_Store``, etc.).  Set
            ``False`` to include them.
    """

    def __init__(self, *, skip_hidden: bool = True) -> None:
        self._skip_hidden = skip_hidden

    def can_read(self, path: str) -> bool:
        """Return True for plain directories without RO-Crate metadata.

        Returns ``False`` for files, nonexistent paths, and directories
        that contain ``ro-crate-metadata.json`` (deferring those to
        :class:`ROCrateReader`).
        """
        p = Path(path)
        if not p.is_dir():
            return False
        return not (p / _METADATA_FILENAME).is_file()

    def read(self, path: str) -> Graph:
        """Read *path* and return a populated Graph."""
        root = Path(path).resolve()
        if not root.exists():
            msg = f"Path does not exist: {path}"
            raise FileNotFoundError(msg)
        if not root.is_dir():
            msg = f"Path is not a directory: {path}"
            raise NotADirectoryError(msg)

        source = str(root)
        graph = Graph(
            source=source,
            metadata={"_root_id": "./", "name": root.name},
        )
        graph._add_node(
            Entity(
                id="./",
                types=("Dataset",),
                properties={"name": root.name, "_is_root": True},
                source=source,
            )
        )

        for current_dir, dirnames, filenames in root.walk(
            follow_symlinks=False,
            on_error=self._on_walk_error,
        ):
            # Filter in-place so Path.walk skips symlinks/hidden subdirs.
            self._filter_in_place(current_dir, dirnames)
            self._filter_in_place(current_dir, filenames)
            # Sort dirnames so Path.walk descends into subdirs in a
            # deterministic order across filesystems.
            dirnames.sort()

            rel = current_dir.relative_to(root).as_posix()
            parent_id = "./" if rel in ("", ".") else f"{rel}/"

            # Merge dirs and files into one alphabetically sorted sequence
            # so mixed siblings (e.g. "a.txt" next to "zdir/") interleave
            # correctly in insertion order — graph.entities / relationships
            # preserve that order, and CSV/GraphML writers serialise it.
            merged = sorted([(n, True) for n in dirnames] + [(n, False) for n in filenames])

            for name, is_dir in merged:
                if is_dir:
                    child_id = f"{name}/" if rel in ("", ".") else f"{rel}/{name}/"
                    graph._add_node(
                        Entity(
                            id=child_id,
                            types=("Dataset",),
                            properties={"name": name},
                            source=source,
                        )
                    )
                else:
                    entry = current_dir / name
                    try:
                        size = entry.stat().st_size
                    except OSError as exc:
                        warnings.warn(
                            f"Skipped file {entry}: {exc}",
                            stacklevel=2,
                        )
                        continue
                    props: dict = {"name": name, "contentSize": size}
                    mime = mimetypes.guess_type(name)[0]
                    if mime is not None:
                        props["encodingFormat"] = mime
                    child_id = name if rel in ("", ".") else f"{rel}/{name}"
                    graph._add_node(
                        Entity(
                            id=child_id,
                            types=("File",),
                            properties=props,
                            source=source,
                        )
                    )
                graph._add_edge(
                    Relationship(
                        source=parent_id,
                        target=child_id,
                        type="hasPart",
                    )
                )

        return graph

    # --- Helpers ---

    def _filter_in_place(self, current_dir: Path, names: list[str]) -> None:
        """Drop symlinks and (if configured) hidden entries from *names*."""
        kept: list[str] = []
        for name in names:
            if (current_dir / name).is_symlink():
                continue
            if self._skip_hidden and name.startswith("."):
                continue
            kept.append(name)
        names[:] = kept

    def _on_walk_error(self, exc: OSError) -> None:
        """Warn and continue when Path.walk hits an OSError."""
        warnings.warn(f"Skipped during walk: {exc}", stacklevel=2)
