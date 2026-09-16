"""Tests for Graph.where() — property filtering."""

from __future__ import annotations

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship


def _build_graph() -> Graph:
    g = Graph()
    g._add_node(
        Entity(id="#a", types=["Person"], properties={"name": "Alice", "birth_year": 1837})
    )
    g._add_node(Entity(id="#b", types=["Person"], properties={"name": "Bob", "birth_year": 1901}))
    g._add_node(
        Entity(id="#c", types=["Person"], properties={"name": "Carol", "birth_year": 1850})
    )
    g._add_node(Entity(id="#d", types=["Organisation"], properties={"name": "ACME"}))
    g._add_edge(Relationship(source="#a", target="#d", type="memberOf"))
    g._add_edge(Relationship(source="#b", target="#d", type="memberOf"))
    return g


class TestWhereExactMatch:
    def test_match_string(self):
        g = _build_graph()
        result = g.where(name="Alice")
        assert len(result) == 1
        assert result.entities[0].id == "#a"

    def test_match_int(self):
        g = _build_graph()
        result = g.where(birth_year=1837)
        assert len(result) == 1
        assert result.entities[0].id == "#a"

    def test_no_match(self):
        g = _build_graph()
        result = g.where(name="Nonexistent")
        assert len(result) == 0

    def test_missing_property(self):
        g = _build_graph()
        # Organisation has no birth_year.
        result = g.where(birth_year=1837)
        assert "#d" not in result._entities


class TestWhereRange:
    def test_range_inclusive(self):
        g = _build_graph()
        result = g.where(birth_year=(1837, 1850))
        assert len(result) == 2
        ids = {e.id for e in result.entities}
        assert ids == {"#a", "#c"}

    def test_range_single_match(self):
        g = _build_graph()
        result = g.where(birth_year=(1900, 1910))
        assert len(result) == 1
        assert result.entities[0].id == "#b"

    def test_range_no_match(self):
        g = _build_graph()
        result = g.where(birth_year=(2000, 2100))
        assert len(result) == 0


class TestWhereMultipleFilters:
    def test_multiple_conditions(self):
        g = _build_graph()
        result = g.where(name="Alice", birth_year=1837)
        assert len(result) == 1
        assert result.entities[0].id == "#a"

    def test_conflicting_conditions(self):
        g = _build_graph()
        result = g.where(name="Alice", birth_year=1901)
        assert len(result) == 0


class TestWherePreservesEdges:
    def test_edges_between_matching_entities(self):
        g = _build_graph()
        result = g.where(name="Alice")
        # Alice alone — no edges (ACME not in result).
        assert len(result.relationships) == 0

    def test_edges_preserved_when_both_endpoints_match(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"], properties={"team": "blue"}))
        g._add_node(Entity(id="#b", types=["Person"], properties={"team": "blue"}))
        g._add_edge(Relationship(source="#a", target="#b", type="knows"))
        result = g.where(team="blue")
        assert len(result.relationships) == 1


class TestWhereEmpty:
    def test_no_filters_returns_full_graph(self):
        g = _build_graph()
        result = g.where()
        assert len(result) == len(g)


class TestWhereListValues:
    """List-valued properties match when any element satisfies the filter.

    RO-Crate JSON-LD may wrap a single value in a one-item list, and
    ``annotate_entities`` callables commonly return lists, so ``where()``
    must test membership rather than list-vs-scalar equality.
    """

    def _graph(self) -> Graph:
        g = Graph()
        g._add_node(
            Entity(
                id="#a",
                types=["Person"],
                properties={"name": ["Alice"], "roles": ["Geologist", "Lawyer"], "years": [1837]},
            )
        )
        g._add_node(
            Entity(
                id="#b",
                types=["Person"],
                properties={"name": "Bob", "roles": ["Chemist"], "years": [1901, 1950]},
            )
        )
        g._add_node(Entity(id="#c", types=["Person"], properties={"roles": [], "years": []}))
        return g

    def test_scalar_matches_single_item_list(self):
        result = self._graph().where(name="Alice")
        assert {e.id for e in result.entities} == {"#a"}

    def test_scalar_matches_member_of_multi_valued_list(self):
        result = self._graph().where(roles="Lawyer")
        assert {e.id for e in result.entities} == {"#a"}

    def test_scalar_absent_from_list_does_not_match(self):
        assert len(self._graph().where(roles="Botanist")) == 0

    def test_empty_list_does_not_match(self):
        assert "#c" not in self._graph().where(roles="Lawyer")._entities

    def test_range_matches_any_list_element(self):
        result = self._graph().where(years=(1900, 1910))
        assert {e.id for e in result.entities} == {"#b"}

    def test_range_no_element_in_range(self):
        assert len(self._graph().where(years=(2000, 2100))) == 0

    def test_whole_list_equality_still_matches(self):
        result = self._graph().where(roles=["Geologist", "Lawyer"])
        assert {e.id for e in result.entities} == {"#a"}

    def test_tuple_valued_property_matches_member(self):
        g = Graph()
        g._add_node(
            Entity(id="#t", types=["Person"], properties={"roles": ("Geologist", "Lawyer")})
        )
        assert {e.id for e in g.where(roles="Lawyer").entities} == {"#t"}

    def test_range_filter_never_matches_by_tuple_equality(self):
        g = Graph()
        g._add_node(Entity(id="#t", types=["Thing"], properties={"years": (1910, 1900)}))
        # (1910, 1900) is a reversed, empty range; nothing can fall inside it.
        assert len(g.where(years=(1910, 1900))) == 0

    def test_range_applies_to_each_tuple_element(self):
        g = Graph()
        g._add_node(Entity(id="#t", types=["Thing"], properties={"years": (1837, 1901)}))
        assert {e.id for e in g.where(years=(1900, 1910)).entities} == {"#t"}


class TestWhereNone:
    def test_none_inside_list_is_ignored(self):
        g = Graph()
        g._add_node(Entity(id="#n", types=["Thing"], properties={"v": [None]}))
        g._add_node(Entity(id="#m", types=["Thing"], properties={"v": [None, "x"]}))
        assert len(g.where(v=None)) == 0
        assert {e.id for e in g.where(v="x").entities} == {"#m"}

    def test_scalar_none_never_matches(self):
        g = Graph()
        g._add_node(Entity(id="#n", types=["Thing"], properties={"v": None}))
        assert len(g.where(v=None)) == 0


class TestWhereAfterAnnotate:
    def test_annotate_list_field_then_where_on_member(self):
        g = Graph()
        g._add_node(
            Entity(id="#a", types=["Person"], properties={"function": "Geologist, Lawyer"})
        )
        g._add_node(Entity(id="#b", types=["Person"], properties={"function": "Chemist"}))
        annotated = g.annotate_entities(
            roles=lambda e: [r.strip() for r in (e.get("function") or "").split(",")]
        )
        assert annotated.get("#a").properties["roles"] == ["Geologist", "Lawyer"]
        assert {e.id for e in annotated.where(roles="Lawyer").entities} == {"#a"}
