"""TypeRegistry — dynamic type and relationship discovery with fuzzy validation."""

from __future__ import annotations

from rapidfuzz import process


class TypeRegistry:
    """Dynamically exposes entity or relationship types as attributes.

    Used as ``graph.types`` and ``graph.relationship_types``.  Supports
    attribute access for autocomplete (``graph.types.Person``) and fuzzy
    string validation with helpful error messages.

    Instances are immutable snapshots — call ``_with_types()`` to produce
    a new registry scoped to a subset.
    """

    def __init__(self, names: frozenset[str], *, label: str = "type") -> None:
        self._names = names
        self._label = label  # "entity type" or "relationship type", used in errors

    # --- Public API ---

    def __contains__(self, name: str) -> bool:
        return name in self._names

    def __iter__(self):
        return iter(sorted(self._names))

    def __len__(self) -> int:
        return len(self._names)

    def __repr__(self) -> str:
        sorted_names = sorted(self._names)
        if len(sorted_names) <= 10:
            listing = ", ".join(sorted_names)
        else:
            listing = (
                ", ".join(sorted_names[:10]) + f", ... ({len(sorted_names)} total)"
            )
        return f"TypeRegistry([{listing}])"

    def __getattr__(self, name: str) -> str:
        """Allow ``registry.Person`` → ``"Person"`` with fuzzy fallback."""
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._names:
            return name
        self._raise_not_found(name)

    def validate(self, name: str) -> str:
        """Validate *name* against known types, returning it if valid.

        Raises ``ValueError`` with fuzzy suggestions if not found.
        """
        if name in self._names:
            return name
        self._raise_not_found(name)

    def _with_types(self, names: frozenset[str]) -> TypeRegistry:
        """Return a new registry scoped to *names*."""
        return TypeRegistry(names, label=self._label)

    # --- Error helpers ---

    def _raise_not_found(self, name: str) -> None:
        available = sorted(self._names)
        if not available:
            msg = f'"{name}" is not a recognised {self._label} (no types loaded yet).'
            raise ValueError(msg)

        matches = process.extract(name, available, limit=3, score_cutoff=50)
        suggestions = [m[0] for m in matches]

        if suggestions:
            suggestion_str = ", ".join(f'"{s}"' for s in suggestions)
            msg = f'"{name}" isn\'t a recognised {self._label}. Did you mean {suggestion_str}?'
        else:
            if len(available) <= 10:
                available_str = ", ".join(available)
            else:
                available_str = (
                    ", ".join(available[:10]) + f", ... ({len(available)} total)"
                )
            msg = f'"{name}" isn\'t a recognised {self._label}. Available: {available_str}'
        raise ValueError(msg)
