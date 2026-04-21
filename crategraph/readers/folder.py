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

from crategraph.core.graph import Graph
from crategraph.core.interfaces import Reader


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
        raise NotImplementedError

    def read(self, path: str) -> Graph:
        raise NotImplementedError
