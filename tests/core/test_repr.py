"""Tests for Entity, Relationship, and Graph display (__repr__, _repr_html_)."""

from __future__ import annotations

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship


def _build_graph() -> Graph:
    g = Graph(source="test.zip")
    g._add_node(Entity(id="#a", types=["Person"], properties={"name": "Alice"}))
    g._add_node(
        Entity(id="#b", types=["Organisation"], properties={"name": "Uni of Melbourne"})
    )
    g._add_edge(Relationship(source="#a", target="#b", type="memberOf"))
    return g


def _build_large_graph(n: int = 40) -> Graph:
    """Build a graph with *n* entities to trigger the summary view."""
    g = Graph()
    for i in range(n):
        g._add_node(
            Entity(id=f"#{i}", types=[f"Type{i % 5}"], properties={"name": f"E{i}"})
        )
    for i in range(n - 1):
        g._add_edge(Relationship(source=f"#{i}", target=f"#{i + 1}", type="link"))
    return g


# --- Entity repr ---


class TestEntityRepr:
    def test_repr_with_name(self):
        e = Entity(id="#a", types=["Person"], properties={"name": "Alice"})
        assert repr(e) == "Entity('Person', 'Alice', id='#a')"

    def test_repr_without_name(self):
        e = Entity(id="#xyz", types=["Place"])
        assert repr(e) == "Entity('Place', '#xyz', id='#xyz')"

    def test_name_property_from_properties(self):
        e = Entity(id="#a", types=["Person"], properties={"name": "Alice"})
        assert e.name == "Alice"

    def test_name_property_falls_back_to_id(self):
        e = Entity(id="#a", types=["Person"])
        assert e.name == "#a"


class TestEntityHtml:
    def test_html_matches_repr_content(self):
        e = Entity(id="#a", types=["Person"], properties={"name": "Alice"})
        html = e._repr_html_()
        assert "Person" in html
        assert "Alice" in html
        assert "#a" in html

    def test_html_is_monospace_pre(self):
        e = Entity(id="#a", types=["Person"], properties={"name": "Alice"})
        html = e._repr_html_()
        assert "<pre" in html

    def test_html_escapes_special_chars(self):
        e = Entity(
            id="#a",
            types=["Person"],
            properties={"name": "<script>alert('xss')</script>"},
        )
        html = e._repr_html_()
        assert "<script>" not in html


# --- Relationship repr ---


class TestRelationshipRepr:
    def test_repr_format(self):
        r = Relationship(source="#a", target="#b", type="memberOf")
        assert repr(r) == "Relationship('#a' --memberOf--> '#b')"


# --- Graph repr ---


class TestRepr:
    def test_repr_format(self):
        g = _build_graph()
        r = repr(g)
        assert "2 entities" in r
        assert "1 relationships" in r
        assert "test.zip" in r

    def test_repr_empty_graph(self):
        g = Graph()
        r = repr(g)
        assert "0 entities" in r
        assert "0 relationships" in r

    def test_repr_no_source(self):
        g = Graph()
        r = repr(g)
        assert "source" not in r


class TestReprHtml:
    def test_html_contains_counts(self):
        g = _build_graph()
        html = g._repr_html_()
        assert "2" in html
        assert "1" in html

    def test_html_contains_source(self):
        g = _build_graph()
        html = g._repr_html_()
        assert "test.zip" in html

    def test_html_is_monospace_pre(self):
        g = _build_graph()
        html = g._repr_html_()
        assert "<pre" in html

    def test_html_no_tables(self):
        g = _build_graph()
        html = g._repr_html_()
        assert "<table" not in html

    def test_html_shows_top_types(self):
        g = _build_large_graph(40)
        html = g._repr_html_()
        assert "Type0" in html

    def test_html_collapses_extra_types(self):
        g = _build_large_graph(40)
        html = g._repr_html_()
        # 5 types total (Type0-Type4), show top 4, collapse 1
        assert "+1 more" in html

    def test_html_no_source_line_when_none(self):
        g = Graph()
        html = g._repr_html_()
        assert "Source" not in html and "None" not in html
