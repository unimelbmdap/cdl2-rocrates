"""Reader plugins for loading graph data from various formats."""

from crategraph.readers.folder import SimpleFolderReader
from crategraph.readers.okf import OKFReader

__all__ = ["OKFReader", "SimpleFolderReader"]
