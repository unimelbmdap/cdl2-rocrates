"""Tests for Graph.simplify() — iterative leaf removal (k-core peeling)."""

from __future__ import annotations

import warnings

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship

# --- helpers ---


def _make_graph(entities: list[Entity], relationships: list[Relationship]) -> Graph:
    """Build a small Graph from explicit entities and relationships."""
    g = Graph(source="test")
    for e in entities:
        g._add_node(e)
    for r in relationships:
        g._add_edge(r)
    return g


def _star(centre: str = "hub", n_leaves: int = 4) -> Graph:
    """Star graph: one hub connected to *n_leaves* leaf nodes."""
    hub = Entity(id=centre, types=["Organisation"])
    leaves = [Entity(id=f"leaf-{i}", types=["File"]) for i in range(n_leaves)]
    rels = [Relationship(source=centre, target=f"leaf-{i}", type="has") for i in range(n_leaves)]
    return _make_graph([hub, *leaves], rels)


def _chain(length: int = 5) -> Graph:
    """Linear chain: n0 -> n1 -> n2 -> ... -> n(length-1)."""
    entities = [Entity(id=f"n{i}", types=["Person"]) for i in range(length)]
    rels = [
        Relationship(source=f"n{i}", target=f"n{i + 1}", type="knows") for i in range(length - 1)
    ]
    return _make_graph(entities, rels)


def _triangle_with_tails() -> Graph:
    """Three-node cycle (a-b-c) with a leaf hanging off each vertex."""
    core = [
        Entity(id="a", types=["Organisation"]),
        Entity(id="b", types=["Organisation"]),
        Entity(id="c", types=["Organisation"]),
    ]
    tails = [
        Entity(id="ta", types=["File"]),
        Entity(id="tb", types=["File"]),
        Entity(id="tc", types=["Dataset"]),
    ]
    rels = [
        Relationship(source="a", target="b", type="link"),
        Relationship(source="b", target="c", type="link"),
        Relationship(source="c", target="a", type="link"),
        Relationship(source="a", target="ta", type="has"),
        Relationship(source="b", target="tb", type="has"),
        Relationship(source="c", target="tc", type="has"),
    ]
    return _make_graph(core + tails, rels)


# --- test classes ---


class TestBasicSimplification:
    """Leaf removal with default min_connections=2."""

    def test_star_returns_self_with_warning(self):
        g = _star()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = g.simplify()
            assert result is g
            assert len(w) == 1
            assert "fully simplified" in str(w[0].message)

    def test_triangle_preserves_core(self):
        g = _triangle_with_tails()
        simplified = g.simplify()
        assert len(simplified) == 3
        assert all(eid in simplified._entities for eid in ["a", "b", "c"])
        assert all(eid not in simplified._entities for eid in ["ta", "tb", "tc"])

    def test_chain_returns_self_with_warning(self):
        """A linear chain has no node with degree >= 2 (endpoints have 1, interior cascades)."""
        g = _chain(5)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = g.simplify()
            assert result is g
            assert len(w) == 1


class TestMinConnectionsThreshold:
    """Higher min_connections is more aggressive."""

    def test_min3_returns_self_with_warning(self):
        g = _triangle_with_tails()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = g.simplify(min_connections=3)
            assert result is g
            assert len(w) == 1

    def test_min1_keeps_everything_connected(self):
        g = _triangle_with_tails()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            simplified = g.simplify(min_connections=1)
            # Every node has at least 1 connection — already stable
            assert simplified is g
            assert len(simplified) == 6
            assert len(w) == 1


class TestChaining:
    """Auto-escalating k via chained simplify() calls."""

    def test_chained_simplify_escalates_k(self):
        """Build a graph where k=2 and k=3 give different non-empty results."""
        # Triangle (a-b-c) + K4 cluster (d-e-f-g) + bridge b-d + leaves on a,b,c
        entities = [
            Entity(id="a", types=["Organisation"]),
            Entity(id="b", types=["Organisation"]),
            Entity(id="c", types=["Organisation"]),
            Entity(id="a1", types=["Person"]),
            Entity(id="a2", types=["Person"]),
            Entity(id="b1", types=["Person"]),
            Entity(id="b2", types=["Person"]),
            Entity(id="c1", types=["Person"]),
            Entity(id="c2", types=["Person"]),
            Entity(id="d", types=["Project"]),
            Entity(id="e", types=["Project"]),
            Entity(id="f", types=["Project"]),
            Entity(id="g", types=["Project"]),
        ]
        rels = [
            Relationship(source="a", target="b", type="link"),
            Relationship(source="b", target="c", type="link"),
            Relationship(source="c", target="a", type="link"),
            Relationship(source="a", target="a1", type="has"),
            Relationship(source="a", target="a2", type="has"),
            Relationship(source="b", target="b1", type="has"),
            Relationship(source="b", target="b2", type="has"),
            Relationship(source="c", target="c1", type="has"),
            Relationship(source="c", target="c2", type="has"),
            Relationship(source="b", target="d", type="link"),
            Relationship(source="d", target="e", type="link"),
            Relationship(source="d", target="f", type="link"),
            Relationship(source="d", target="g", type="link"),
            Relationship(source="e", target="f", type="link"),
            Relationship(source="e", target="g", type="link"),
            Relationship(source="f", target="g", type="link"),
        ]
        g = _make_graph(entities, rels)
        assert len(g) == 13

        s1 = g.simplify()  # k=2: removes 6 leaves
        assert len(s1) == 7
        assert s1._simplification_k == 2

        s2 = s1.simplify()  # k=3: removes a, b, c (cascade)
        assert len(s2) == 4
        assert set(s2._entities.keys()) == {"d", "e", "f", "g"}
        assert s2._simplification_k == 3

    def test_chained_simplify_stabilises(self):
        """When further simplification would annihilate, returns self with warning."""
        g = _triangle_with_tails()
        s1 = g.simplify()  # k=2: keeps triangle
        assert len(s1) == 3

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            s2 = s1.simplify()  # k=3: would annihilate → returns s1
            assert s2 is s1
            assert len(w) == 1
            assert "fully simplified" in str(w[0].message)


class TestAnnotations:
    """Surviving nodes gain a 'simplified' property."""

    def test_simplified_property_present(self):
        g = _triangle_with_tails()
        simplified = g.simplify()
        a = simplified._entities["a"]
        assert "simplified" in a.properties
        assert a.properties["simplified"] == {"File": 1}

    def test_simplified_counts_by_type(self):
        g = _triangle_with_tails()
        simplified = g.simplify()
        c_entity = simplified._entities["c"]
        assert c_entity.properties["simplified"] == {"Dataset": 1}

    def test_simplified_entities_carry_annotation(self):
        g = _triangle_with_tails()
        simplified = g.simplify()
        a_entity = simplified._entities["a"]
        assert a_entity.properties["simplified"] == {"File": 1}

    def test_no_annotation_when_no_neighbours_removed(self):
        """A node whose removed-neighbour count is zero gets no annotation."""
        entities = [Entity(id=f"q{i}", types=["Person"]) for i in range(4)]
        rels = [
            Relationship(source=f"q{i}", target=f"q{j}", type="link")
            for i in range(4)
            for j in range(i + 1, 4)
        ]
        g = _make_graph(entities, rels)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            simplified = g.simplify()
            # Fully connected — returns self, no annotations
            assert simplified is g
            for e in simplified._entities.values():
                assert "simplified" not in e.properties


class TestEdgeCases:
    """Empty, fully connected, and isolated graphs."""

    def test_empty_graph(self):
        g = Graph(source="empty")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = g.simplify()
            assert result is g
            assert len(w) == 1

    def test_fully_connected(self):
        entities = [Entity(id=f"n{i}", types=["Person"]) for i in range(4)]
        rels = [
            Relationship(source=f"n{i}", target=f"n{j}", type="link")
            for i in range(4)
            for j in range(i + 1, 4)
        ]
        g = _make_graph(entities, rels)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            simplified = g.simplify()
            # Already fully connected — returns self
            assert simplified is g
            assert len(simplified) == 4
            assert len(w) == 1

    def test_single_isolated_node(self):
        g = _make_graph([Entity(id="alone", types=["Person"])], [])
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = g.simplify()
            assert result is g
            assert len(w) == 1


class TestRelationshipsFiltered:
    """Edges involving removed nodes must be excluded."""

    def test_edges_filtered(self):
        g = _triangle_with_tails()
        simplified = g.simplify()
        for rel in simplified._relationships:
            assert rel.source in simplified._entities
            assert rel.target in simplified._entities
        assert len(simplified._relationships) == 3


class TestImmutabilityAndStability:
    """Original graph unchanged; simplify on stable graph returns self."""

    def test_original_unchanged(self):
        g = _triangle_with_tails()
        original_count = len(g)
        _ = g.simplify()
        assert len(g) == original_count

    def test_double_simplify_stable(self):
        g = _triangle_with_tails()
        once = g.simplify()
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            twice = once.simplify()
        assert twice is once


class TestRootPreserved:
    """_root reference is preserved so expand() can recover removed nodes."""

    def test_root_is_original(self):
        g = _triangle_with_tails()
        simplified = g.simplify()
        assert simplified._root is g

    def test_expand_recovers_removed(self):
        g = _triangle_with_tails()
        simplified = g.simplify()
        expanded = simplified.expand()
        assert len(expanded) > len(simplified)
        assert "ta" in expanded._entities
        assert "tb" in expanded._entities
        assert "tc" in expanded._entities
