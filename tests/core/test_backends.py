"""Parametrised tests for GraphBackend implementations."""

from __future__ import annotations

import pytest

from crategraph.core.backends.networkx import NetworkXBackend
from crategraph.core.interfaces import GraphBackend
from crategraph.core.models import Entity, Relationship


def _make_rustworkx_backend():
    """Import and return a RustworkxBackend, or skip if not installed."""
    rx = pytest.importorskip("rustworkx")  # noqa: F841
    from crategraph.core.backends.rustworkx import RustworkxBackend

    return RustworkxBackend()


@pytest.fixture(params=["networkx", "rustworkx"])
def backend(request: pytest.FixtureRequest) -> GraphBackend:
    if request.param == "networkx":
        return NetworkXBackend()
    return _make_rustworkx_backend()


# --- Protocol conformance ---


class TestABCConformance:
    def test_networkx_is_graph_backend(self):
        assert issubclass(NetworkXBackend, GraphBackend)

    def test_rustworkx_is_graph_backend(self):
        pytest.importorskip("rustworkx")
        from crategraph.core.backends.rustworkx import RustworkxBackend

        assert issubclass(RustworkxBackend, GraphBackend)


# --- Parametrised backend behaviour ---


class TestAddNode:
    def test_add_and_has_node(self, backend: GraphBackend):
        e = Entity(id="#a", types=["Person"])
        backend.add_node("#a", e)
        assert backend.has_node("#a")

    def test_has_node_returns_false_for_missing(self, backend: GraphBackend):
        assert not backend.has_node("#missing")

    def test_add_duplicate_node_updates(self, backend: GraphBackend):
        e1 = Entity(id="#a", types=["Person"], properties={"name": "Alice"})
        e2 = Entity(id="#a", types=["Person"], properties={"name": "Alice B."})
        backend.add_node("#a", e1)
        backend.add_node("#a", e2)
        # Node still exists (no crash, no duplicate).
        assert backend.has_node("#a")


class TestAddEdge:
    def test_add_edge(self, backend: GraphBackend):
        backend.add_node("#a", Entity(id="#a", types=["Person"]))
        backend.add_node("#b", Entity(id="#b", types=["File"]))
        r = Relationship(source="#a", target="#b", type="author")
        backend.add_edge("#a", "#b", "author", r)
        assert "#b" in backend.successors("#a")

    def test_multiple_edges(self, backend: GraphBackend):
        backend.add_node("#a", Entity(id="#a", types=["Person"]))
        backend.add_node("#b", Entity(id="#b", types=["File"]))
        r1 = Relationship(source="#a", target="#b", type="author")
        r2 = Relationship(source="#a", target="#b", type="contributor")
        backend.add_edge("#a", "#b", "author", r1)
        backend.add_edge("#a", "#b", "contributor", r2)
        assert "#b" in backend.successors("#a")


class TestSuccessorsAndPredecessors:
    def _build(self, backend: GraphBackend) -> None:
        backend.add_node("#a", Entity(id="#a", types=["Person"]))
        backend.add_node("#b", Entity(id="#b", types=["File"]))
        backend.add_node("#c", Entity(id="#c", types=["Dataset"]))
        r1 = Relationship(source="#a", target="#b", type="author")
        r2 = Relationship(source="#b", target="#c", type="hasPart")
        backend.add_edge("#a", "#b", "author", r1)
        backend.add_edge("#b", "#c", "hasPart", r2)

    def test_successors(self, backend: GraphBackend):
        self._build(backend)
        assert backend.successors("#a") == {"#b"}

    def test_predecessors(self, backend: GraphBackend):
        self._build(backend)
        assert backend.predecessors("#b") == {"#a"}

    def test_middle_node_has_both(self, backend: GraphBackend):
        self._build(backend)
        assert backend.successors("#b") == {"#c"}
        assert backend.predecessors("#b") == {"#a"}

    def test_leaf_has_no_successors(self, backend: GraphBackend):
        self._build(backend)
        assert backend.successors("#c") == set()

    def test_root_has_no_predecessors(self, backend: GraphBackend):
        self._build(backend)
        assert backend.predecessors("#a") == set()


class TestSubgraph:
    """Parametrised tests for backend.subgraph()."""

    @staticmethod
    def _build_entities_and_relationships():
        entities = {
            "#a": Entity(id="#a", types=["Person"]),
            "#b": Entity(id="#b", types=["File"]),
            "#c": Entity(id="#c", types=["Dataset"]),
        }
        relationships = [
            Relationship(source="#a", target="#b", type="author"),
            Relationship(source="#b", target="#c", type="hasPart"),
            Relationship(source="#a", target="#c", type="creator"),
        ]
        return entities, relationships

    def _populate(self, backend, entities, relationships):
        for nid, entity in entities.items():
            backend.add_node(nid, entity)
        for rel in relationships:
            backend.add_edge(rel.source, rel.target, rel.type, rel)

    def test_subgraph_contains_correct_nodes(self, backend: GraphBackend):
        entities, relationships = self._build_entities_and_relationships()
        self._populate(backend, entities, relationships)
        sub = backend.subgraph({"#a", "#b"}, entities, relationships)
        assert sub.has_node("#a")
        assert sub.has_node("#b")
        assert not sub.has_node("#c")

    def test_subgraph_contains_mutual_edges_only(self, backend: GraphBackend):
        entities, relationships = self._build_entities_and_relationships()
        self._populate(backend, entities, relationships)
        sub = backend.subgraph({"#a", "#b"}, entities, relationships)
        # #a -> #b edge should be present
        assert "#b" in sub.successors("#a")
        # Edges to #c should be excluded
        assert sub.successors("#b") == set()
        assert "#c" not in sub.successors("#a")

    def test_subgraph_empty_node_ids(self, backend: GraphBackend):
        entities, relationships = self._build_entities_and_relationships()
        self._populate(backend, entities, relationships)
        sub = backend.subgraph(set(), entities, relationships)
        assert not sub.has_node("#a")
        assert not sub.has_node("#b")
        assert not sub.has_node("#c")
