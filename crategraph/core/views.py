"""Graph-aware, ephemeral views over the immutable models.

``EntityView`` wraps an :class:`~crategraph.core.models.Entity` and a
``Graph`` reference, exposing a *record-style* surface (matching
``entity_records``/``_derive_label``, deliberately NOT
``Entity.type``/``Entity.name``) plus one-hop traversal via
``related``/``has``. ``Related`` is the collection ``related`` returns.
``CardinalityError`` is colocated here because it is raised by
``Related.first(strict=True)`` and the codebase has no
exceptions-module convention (bare builtins inline).

Dependency direction is one-way: this module imports ``Graph`` only
under ``TYPE_CHECKING``; it receives a ``Graph`` instance and reads
adjacency through the narrow ``Graph._related_ids`` primitive.
"""

from __future__ import annotations


class CardinalityError(ValueError):
    """Raised when a single value was required but several were found.

    Subclasses ``ValueError`` so existing ``except ValueError`` handlers
    still catch it. Raised by :meth:`Related.first` with ``strict=True``.
    """
