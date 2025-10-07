"""RO-Crate analysis and visualisation.

This module provides classes for working with RO-Crate collections.
"""

from typing import List


class Crate:
    """Work with an RO-Crate.

    Main class for analysing and visualising RO-Crate data.

    Attributes:
        path: Path to the RO-Crate directory or file.

    Examples:
        >>> crate = Crate("/path/to/crate")
        >>> entities = crate.get_entities()
    """

    def __init__(self, path: str) -> None:
        """Initialise a Crate object.

        Args:
            path: Path to the RO-Crate directory or file.
        """
        self.path = path

    def get_entities(self) -> List:
        """Get all entities in the crate.

        Returns:
            List of entities from the crate.
        """
        # Placeholder implementation
        return []


class CrateSet:
    """Work with multiple RO-Crates.

    Analyse and compare multiple crates together.

    Attributes:
        crates: List of Crate objects in the set.

    Examples:
        >>> crate_set = CrateSet()
        >>> crate_set.add("/path/to/crate1")
        >>> crate_set.add("/path/to/crate2")
    """

    def __init__(self) -> None:
        """Initialise an empty crate set."""
        self.crates: List[Crate] = []

    def add(self, path: str) -> None:
        """Add a crate to the set.

        Args:
            path: Path to the RO-Crate directory or file.
        """
        self.crates.append(Crate(path))
