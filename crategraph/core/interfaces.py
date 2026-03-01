"""ABCs: Reader, Writer, Validator, Renderer, and internal GraphBackend."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from crategraph.core.graph import Graph
    from crategraph.core.models import Entity, FileInfo, Relationship, ValidationReport


# --- Internal backend ABC ---


class GraphBackend(ABC):
    """Base class for graph storage engines (NetworkX, rustworkx, etc.).

    All identifiers are string-based — backends that use integer indices
    (e.g. rustworkx) must maintain their own internal mapping.
    """

    @abstractmethod
    def add_node(self, node_id: str, entity: Entity) -> None:
        """Add or replace a node."""

    @abstractmethod
    def add_edge(
        self, source: str, target: str, key: str, relationship: Relationship
    ) -> None:
        """Add a directed edge."""

    @abstractmethod
    def has_node(self, node_id: str) -> bool:
        """Return True if *node_id* exists in the graph."""

    @abstractmethod
    def successors(self, node_id: str) -> set[str]:
        """Return IDs of all direct successors of *node_id*."""

    @abstractmethod
    def predecessors(self, node_id: str) -> set[str]:
        """Return IDs of all direct predecessors of *node_id*."""

    def subgraph(
        self,
        node_ids: set[str],
        entities: dict[str, Entity],
        relationships: list[Relationship],
    ) -> GraphBackend:
        """Return a new backend containing only *node_ids* and mutual edges.

        Default: loop add_node/add_edge. Backends may override for speed.
        """
        new = type(self)()
        for nid in node_ids:
            if nid in entities:
                new.add_node(nid, entities[nid])
        for rel in relationships:
            if rel.source in node_ids and rel.target in node_ids:
                new.add_edge(rel.source, rel.target, rel.type, rel)
        return new


class Reader(ABC):
    """Base class for graph readers (e.g. RO-Crate, GEXF)."""

    @abstractmethod
    def can_read(self, path: str) -> bool:
        """Return True if this reader can handle the given path."""

    @abstractmethod
    def read(self, path: str) -> Graph:
        """Read the source at *path* and return a populated Graph."""


class Writer(ABC):
    """Base class for graph writers (e.g. JSON-LD, GEXF)."""

    @abstractmethod
    def write(self, graph: Graph, path: str, **kwargs: Any) -> None:
        """Write *graph* to the file at *path*."""


class Validator(ABC):
    """Base class for graph validators (data quality checks)."""

    @abstractmethod
    def validate(self, graph: Graph) -> ValidationReport:
        """Validate *graph* and return a report of issues found."""


class Renderer(ABC):
    """Base class for graph renderers (visualisation backends).

    Concrete renderers should support these common parameters where
    applicable:

    - ``colour_by``: How to assign node colours (e.g. ``"type"``,
      ``"community"``).
    - ``size_by``: How to scale node sizes (e.g. ``"connections"``).
    - ``filepath``: Save output to a file path instead of returning an
      in-memory object.
    - ``height`` / ``width``: Canvas dimensions.

    Renderer-specific parameters can be accepted via ``**kwargs``.
    """

    @abstractmethod
    def render(self, graph: Graph, **kwargs: Any) -> Any:
        """Render *graph* and return the result."""


class Inspector(ABC):
    """Base class for file inspectors.

    Concrete inspectors examine data files referenced by entities and
    return structured information about them.
    """

    @abstractmethod
    def supports(self, entity: Entity) -> bool:
        """Return True if this inspector can handle the entity's file."""

    @abstractmethod
    def inspect(self, path: Path) -> FileInfo:
        """Inspect the file at *path* and return structured info."""
