"""Public API export smoke tests."""

from __future__ import annotations


def test_entity_view_and_related_are_public() -> None:
    import crategraph

    assert hasattr(crategraph, "EntityView")
    assert hasattr(crategraph, "RelationshipView")
    assert hasattr(crategraph, "Related")
    assert hasattr(crategraph, "CardinalityError")
    from crategraph import CardinalityError, EntityView, Related, RelationshipView  # noqa: F401


def test_all_includes_new_and_existing_public_names() -> None:
    import crategraph

    assert set(crategraph.__all__) == {
        "CardinalityError",
        "Corpus",
        "Crate",
        "Entity",
        "EntityView",
        "Graph",
        "Related",
        "Relationship",
        "RelationshipView",
    }
