"""Tests for Graph.get() — single entity access."""

from __future__ import annotations

import pytest

from crategraph.core.graph import Graph
from crategraph.core.models import Entity


class TestGet:
    def test_get_existing(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"], properties={"name": "Alice"}))
        entity = g.get("#a")
        assert entity.id == "#a"
        assert entity.properties["name"] == "Alice"

    def test_get_nonexistent(self):
        g = Graph()
        with pytest.raises(KeyError, match="No entity with id"):
            g.get("#nonexistent")

    def test_get_returns_entity_not_graph(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"]))
        result = g.get("#a")
        assert isinstance(result, Entity)
