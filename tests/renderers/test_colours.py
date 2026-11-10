"""Tests for generic colour resolution."""

from __future__ import annotations

import pytest

from crategraph.core.graph import Graph
from crategraph.core.models import Entity
from crategraph.renderers._colours import (
    normalise_colour_map,
    resolve_colour_groups,
    resolve_entity_colours,
)


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
        cmap = resolve_entity_colours(g, "type")
        assert cmap["#a"] == cmap["#b"]  # same type
        assert cmap["#a"] != cmap["#c"]  # different type

    def test_colour_by_property(self):
        g = _build_graph()
        cmap = resolve_entity_colours(g, "location")
        assert cmap["#a"] == cmap["#c"]  # both Melbourne
        assert cmap["#a"] != cmap["#b"]  # Melbourne vs Sydney

    def test_colour_by_source(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"], source="/data/crate1"))
        g._add_node(Entity(id="#b", types=["Person"], source="/data/crate1"))
        g._add_node(Entity(id="#c", types=["Person"], source="/data/crate2"))
        cmap = resolve_entity_colours(g, "source")
        assert cmap["#a"] == cmap["#b"]
        assert cmap["#a"] != cmap["#c"]

    def test_missing_property_gets_fallback_group(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"], properties={"location": "Melbourne"}))
        g._add_node(Entity(id="#b", types=["Person"], properties={}))
        cmap = resolve_entity_colours(g, "location")
        assert "#a" in cmap and "#b" in cmap

    def test_empty_graph(self):
        assert resolve_entity_colours(Graph(), "type") == {}

    def test_colours_are_hex(self):
        g = _build_graph()
        for colour in resolve_entity_colours(g, "type").values():
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
        cmap = resolve_entity_colours(g, "source")
        # Should group by crate source, not by the property values.
        assert cmap["#a"] == cmap["#b"]  # same crate
        assert cmap["#a"] != cmap["#c"]  # different crate

    def test_community_property_works(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"], properties={"community": 0}))
        g._add_node(Entity(id="#b", types=["Person"], properties={"community": 0}))
        g._add_node(Entity(id="#c", types=["Person"], properties={"community": 1}))
        cmap = resolve_entity_colours(g, "community")
        assert cmap["#a"] == cmap["#b"]
        assert cmap["#a"] != cmap["#c"]


class TestColourMap:
    def test_listed_values_get_their_colour_and_others_keep_theirs(self):
        g = _build_graph()
        before = resolve_entity_colours(g, "location")
        after = resolve_entity_colours(g, "location", {"Sydney": "#123456"})
        assert after["#b"] == "#123456"
        assert after["#a"] == after["#c"] == before["#a"]  # Melbourne untouched

    def test_legend_shows_the_chosen_colours(self):
        _, legend = resolve_colour_groups(_build_graph(), "location", {"Melbourne": "#ABC"})
        assert legend["Melbourne"] == "#aabbcc"
        assert set(legend) == {"Melbourne", "Sydney"}

    def test_keys_are_compared_as_strings(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Event"], properties={"year": 2020}))
        assert resolve_entity_colours(g, "year", {2020: "#010203"}) == {"#a": "#010203"}

    def test_values_absent_from_the_graph_are_ignored(self):
        _, legend = resolve_colour_groups(_build_graph(), "location", {"Perth": "#010203"})
        assert "Perth" not in legend

    @pytest.mark.parametrize(
        "colour", ["red", "#12345", "#gggggg", "123456", "#abc\n", " #abc", 5, None]
    )
    def test_non_hex_colours_raise_value_error(self, colour):
        with pytest.raises(ValueError, match="not a hex colour"):
            normalise_colour_map({"Sydney": colour})

    def test_visualise_rejects_a_bad_colour_before_any_layout(self, monkeypatch):
        g = _build_graph()

        def no_layout(*args, **kwargs):
            raise AssertionError("layout ran before the colour_map was checked")

        monkeypatch.setattr(Graph, "layout", no_layout)
        with pytest.raises(ValueError, match="not a hex colour"):
            g.visualise(colour_map={"Sydney": "red"})

    @pytest.mark.parametrize("colour_map", [[], [("Person", "#abc")], "Person"])
    def test_non_mapping_colour_map_raises_type_error(self, colour_map):
        with pytest.raises(TypeError, match="colour_map must map"):
            normalise_colour_map(colour_map)
        with pytest.raises(TypeError, match="colour_map must map"):
            _build_graph().visualise(renderer="3d", colour_map=colour_map)

    @pytest.mark.parametrize("renderer", ["sigma", "svg", "forcegraph3d", "pyvis"])
    def test_every_renderer_checks_colours_even_for_an_empty_graph(self, renderer):
        if renderer == "pyvis":
            pytest.importorskip("pyvis")
        module = __import__(f"crategraph.renderers.{renderer}", fromlist=["*"])
        cls = next(
            getattr(module, name)
            for name in dir(module)
            if name.endswith("Renderer") and getattr(module, name).__module__ == module.__name__
        )
        with pytest.raises(ValueError, match="not a hex colour"):
            cls().render(Graph(), colour_map={"Person": "red"})
