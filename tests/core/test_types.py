"""Tests for crategraph.core.types — TypeRegistry."""

from __future__ import annotations

import pytest

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship
from crategraph.core.types import TypeRegistry


class TestTypeRegistryBasics:
    def test_contains(self):
        reg = TypeRegistry(frozenset({"Person", "Organisation"}))
        assert "Person" in reg
        assert "Unknown" not in reg

    def test_iter(self):
        reg = TypeRegistry(frozenset({"Person", "Organisation", "Event"}))
        assert list(reg) == ["Event", "Organisation", "Person"]

    def test_len(self):
        reg = TypeRegistry(frozenset({"Person", "Organisation"}))
        assert len(reg) == 2

    def test_repr_short(self):
        reg = TypeRegistry(frozenset({"Person", "Event"}))
        r = repr(reg)
        assert "Person" in r
        assert "Event" in r

    def test_repr_long(self):
        names = frozenset(f"Type{i}" for i in range(20))
        reg = TypeRegistry(names)
        r = repr(reg)
        assert "20 total" in r

    def test_empty_registry(self):
        reg = TypeRegistry(frozenset())
        assert len(reg) == 0
        assert list(reg) == []


class TestAttributeAccess:
    def test_valid_type(self):
        reg = TypeRegistry(frozenset({"Person", "Organisation"}))
        assert reg.Person == "Person"

    def test_invalid_type_with_suggestion(self):
        reg = TypeRegistry(frozenset({"Person", "Organisation"}), label="entity type")
        with pytest.raises(ValueError, match="Person"):
            reg.Persom  # noqa: B018

    def test_private_attr_raises_attribute_error(self):
        reg = TypeRegistry(frozenset({"Person"}))
        with pytest.raises(AttributeError):
            reg._private  # noqa: B018


class TestValidate:
    def test_valid_name(self):
        reg = TypeRegistry(frozenset({"Person", "Organisation"}))
        assert reg.validate("Person") == "Person"

    def test_invalid_name_raises_with_suggestions(self):
        reg = TypeRegistry(frozenset({"Person", "Organisation"}), label="entity type")
        with pytest.raises(ValueError, match="Person"):
            reg.validate("Persom")

    def test_empty_registry_raises(self):
        reg = TypeRegistry(frozenset(), label="entity type")
        with pytest.raises(ValueError, match="no types loaded"):
            reg.validate("Person")

    def test_no_close_match_shows_available(self):
        reg = TypeRegistry(frozenset({"Person", "Event"}), label="entity type")
        with pytest.raises(ValueError, match="Available"):
            reg.validate("zzzzzzzzzzz")


class TestWithTypes:
    def test_scoped_registry(self):
        reg = TypeRegistry(frozenset({"Person", "Organisation", "Event"}))
        scoped = reg._with_types(frozenset({"Person"}))
        assert len(scoped) == 1
        assert "Person" in scoped
        assert "Organisation" not in scoped


class TestGraphIntegration:
    def _build_graph(self) -> Graph:
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"]))
        g._add_node(Entity(id="#b", types=["Organisation"]))
        g._add_node(Entity(id="#c", types=["Person"]))
        g._add_edge(Relationship(source="#a", target="#b", type="memberOf"))
        g._add_edge(Relationship(source="#c", target="#b", type="employedAt"))
        return g

    def test_graph_types(self):
        g = self._build_graph()
        assert "Person" in g.types
        assert "Organisation" in g.types
        assert len(g.types) == 2

    def test_graph_relationship_types(self):
        g = self._build_graph()
        assert "memberOf" in g.relationship_types
        assert "employedAt" in g.relationship_types
        assert len(g.relationship_types) == 2

    def test_empty_graph_types(self):
        g = Graph()
        assert len(g.types) == 0
        assert len(g.relationship_types) == 0

    def test_types_attribute_access(self):
        g = self._build_graph()
        assert g.types.Person == "Person"

    def test_types_fuzzy_error(self):
        g = self._build_graph()
        with pytest.raises(ValueError, match="Person"):
            g.types.validate("Persom")
