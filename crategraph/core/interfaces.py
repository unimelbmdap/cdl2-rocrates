"""ABCs: Reader, Writer, Validator, Renderer, Inspector, and Viewer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from crategraph.core.graph import Graph
    from crategraph.core.models import FileInfo, ValidationReport, ViewInfo


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
    def can_write(self, path: str) -> bool:
        """Return True if this writer can handle the given path."""

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
    def supports(self, path: Path) -> bool:
        """Return True if this inspector can handle the resolved file path."""

    @abstractmethod
    def inspect(self, path: Path) -> FileInfo:
        """Inspect the file at *path* and return structured info."""


class Viewer(ABC):
    """Base class for file viewers.

    Concrete viewers produce rich HTML previews of data files
    referenced by entities — images displayed as images, CSVs as
    interactive tables, audio with playback controls.
    """

    @abstractmethod
    def supports(self, path: Path) -> bool:
        """Return True if this viewer can handle the resolved file path."""

    @abstractmethod
    def view(self, path: Path) -> ViewInfo:
        """View the file at *path* and return a rich HTML preview.

        Implementers must HTML-escape all content derived from file data
        or entity properties before embedding it in the returned
        ``ViewInfo.html``.
        """
