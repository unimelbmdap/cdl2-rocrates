"""Tests for generic colour resolution."""

from __future__ import annotations

from crategraph.core.graph import Graph
from crategraph.core.models import Entity
from crategraph.renderers._colours import resolve_colour_map


def _build_graph() -> Graph:
    g = Graph()
    g._add_node(
        Entity(
            id="#a",
            types=["Person"],
            properties={"name": "Alice", "location": "Melbourne"},
        )
    )
    g._add_node(
        Entity(id="#b", types=["Person"], properties={"name": "Bob", "location": "Sydney"})
    )
    g._add_node(
        Entity(
            id="#c",
            types=["Organisation"],
            properties={"name": "CSIRO", "location": "Melbourne"},
        )
    )
    return g


class TestResolveColourMap:
    def test_colour_by_type(self):
        g = _build_graph()
        cmap = resolve_colour_map(g, "type")
        assert cmap["#a"] == cmap["#b"]  # same type
        assert cmap["#a"] != cmap["#c"]  # different type

    def test_colour_by_property(self):
        g = _build_graph()
        cmap = resolve_colour_map(g, "location")
        assert cmap["#a"] == cmap["#c"]  # both Melbourne
        assert cmap["#a"] != cmap["#b"]  # Melbourne vs Sydney

    def test_colour_by_source(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"], source="/data/crate1"))
        g._add_node(Entity(id="#b", types=["Person"], source="/data/crate1"))
        g._add_node(Entity(id="#c", types=["Person"], source="/data/crate2"))
        cmap = resolve_colour_map(g, "source")
        assert cmap["#a"] == cmap["#b"]
        assert cmap["#a"] != cmap["#c"]

    def test_missing_property_gets_fallback_group(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"], properties={"location": "Melbourne"}))
        g._add_node(Entity(id="#b", types=["Person"], properties={}))
        cmap = resolve_colour_map(g, "location")
        assert "#a" in cmap and "#b" in cmap

    def test_empty_graph(self):
        assert resolve_colour_map(Graph(), "type") == {}

    def test_colours_are_hex(self):
        g = _build_graph()
        for colour in resolve_colour_map(g, "type").values():
            assert colour.startswith("#")

    def test_source_attr_not_shadowed_by_property(self):
        """colour_by='source' should use Entity.source, not properties['source']."""
        g = Graph()
        g._add_node(
            Entity(
                id="#a",
                types=["Relationship"],
                properties={"source": "#person-1"},
                source="/data/crate1",
            )
        )
        g._add_node(
            Entity(
                id="#b",
                types=["Relationship"],
                properties={"source": "#person-2"},
                source="/data/crate1",
            )
        )
        g._add_node(
            Entity(
                id="#c",
                types=["Relationship"],
                properties={"source": "#person-3"},
                source="/data/crate2",
            )
        )
        cmap = resolve_colour_map(g, "source")
        # Should group by crate source, not by the property values.
        assert cmap["#a"] == cmap["#b"]  # same crate
        assert cmap["#a"] != cmap["#c"]  # different crate

    def test_community_property_works(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"], properties={"community": 0}))
        g._add_node(Entity(id="#b", types=["Person"], properties={"community": 0}))
        g._add_node(Entity(id="#c", types=["Person"], properties={"community": 1}))
        cmap = resolve_colour_map(g, "community")
        assert cmap["#a"] == cmap["#b"]
        assert cmap["#a"] != cmap["#c"]
