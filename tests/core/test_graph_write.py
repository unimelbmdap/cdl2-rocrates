"""Tests for Graph.to_networkx() and Graph.write()."""

from __future__ import annotations

import pytest

from crategraph.core.graph import Graph
from crategraph.core.interfaces import Writer
from crategraph.core.models import Entity, Relationship
from crategraph.writers import register_writer
from crategraph.writers.errors import UnknownFormatError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_simple_graph() -> Graph:
    """Return a minimal Graph with two entities and one relationship."""
    g = Graph()
    g._add_node(Entity(id="#alice", types=["Person"], properties={"name": "Alice"}))
    g._add_node(Entity(id="#bob", types=["Person"], properties={"name": "Bob"}))
    g._add_edge(Relationship(source="#alice", target="#bob", type="knows"))
    return g


def _build_graph_with_mutable_entity_props() -> tuple[Graph, str]:
    """Return a Graph with an entity whose properties contain a mutable list."""
    g = Graph()
    entity = Entity(id="#item", types=["Dataset"], properties={"tags": ["a", "b"]})
    g._add_node(entity)
    return g, "#item"


def _build_graph_with_mutable_rel_props() -> tuple[Graph, str, str, str]:
    """Return a Graph with a relationship whose properties contain a mutable list."""
    g = Graph()
    g._add_node(Entity(id="#src", types=["Person"]))
    g._add_node(Entity(id="#tgt", types=["File"]))
    rel = Relationship(
        source="#src",
        target="#tgt",
        type="hasPart",
        properties={"labels": ["x", "y"]},
    )
    g._add_edge(rel)
    return g, "#src", "#tgt", "hasPart"


# ---------------------------------------------------------------------------
# to_networkx tests
# ---------------------------------------------------------------------------


class TestToNetworkx:
    def test_structural_copy_isolation(self):
        """Adding a node to the returned copy does not affect the original graph."""
        graph = _build_simple_graph()
        g = graph.to_networkx()
        g.add_node("__extra__")
        assert "__extra__" not in graph._graph
        assert len(graph.entities) == 2

    def test_deep_copy_entity_property_isolation(self):
        """Mutating entity.properties in the copy does not affect the original."""
        graph, entity_id = _build_graph_with_mutable_entity_props()
        g = graph.to_networkx()
        # Append to the mutable list on the copied node attribute
        g.nodes[entity_id]["entity"].properties["tags"].append("c")
        original_tags = graph.entities[0].properties["tags"]
        assert original_tags == ["a", "b"], (
            "Original entity.properties was mutated via to_networkx() copy"
        )

    def test_deep_copy_relationship_property_isolation(self):
        """Mutating relationship.properties in the copy does not affect the original."""
        graph, src, tgt, rel_type = _build_graph_with_mutable_rel_props()
        g = graph.to_networkx()
        # MultiDiGraph edge data keyed by relationship type
        edge_data = g.get_edge_data(src, tgt, key=rel_type)
        edge_data["relationship"].properties["labels"].append("z")
        original_labels = graph.relationships[0].properties["labels"]
        assert original_labels == ["x", "y"], (
            "Original relationship.properties was mutated via to_networkx() copy"
        )

    def test_copy_false_returns_internal_graph(self):
        """copy=False returns the exact internal _graph object."""
        graph = _build_simple_graph()
        assert graph.to_networkx(copy=False) is graph._graph

    def test_copy_true_returns_different_object(self):
        """copy=True (default) returns a distinct object from _graph."""
        graph = _build_simple_graph()
        g = graph.to_networkx()
        assert g is not graph._graph

    def test_copy_contains_same_nodes(self):
        """The deep copy contains the same node IDs as the original."""
        graph = _build_simple_graph()
        g = graph.to_networkx()
        assert set(g.nodes) == set(graph._graph.nodes)


# ---------------------------------------------------------------------------
# write tests
# ---------------------------------------------------------------------------


class _CaptureWriter(Writer):
    """Writer that records its arguments for inspection."""

    calls: list[tuple]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

    def can_write(self, path: str) -> bool:
        return True

    def write(self, graph: Graph, path: str, **kwargs: object) -> None:
        # Store on the class so tests can inspect across instances
        type(self).calls.append((graph, path, kwargs))


class TestWrite:
    def setup_method(self):
        """Ensure a fresh capture list before each test."""
        _CaptureWriter.calls = []

    def test_write_delegates_to_registered_writer(self):
        """write() instantiates the registered writer and forwards all args."""
        register_writer("_test_fmt_delegate", _CaptureWriter)
        try:
            graph = _build_simple_graph()
            graph.write("some/path", format="_test_fmt_delegate", overwrite=True, extra=42)
            assert len(_CaptureWriter.calls) == 1
            captured_graph, captured_path, captured_kwargs = _CaptureWriter.calls[0]
            assert captured_graph is graph
            assert captured_path == "some/path"
            assert captured_kwargs == {"overwrite": True, "extra": 42}
        finally:
            from crategraph.writers import _REGISTRY

            _REGISTRY.pop("_test_fmt_delegate", None)

    def test_write_missing_format_raises_type_error(self):
        """write() without format= raises TypeError (required kwarg)."""
        graph = _build_simple_graph()
        with pytest.raises(TypeError):
            graph.write("x")  # type: ignore[call-arg]

    def test_write_unknown_format_raises_unknown_format_error(self):
        """write() with an unregistered format name raises UnknownFormatError."""
        graph = _build_simple_graph()
        with pytest.raises(UnknownFormatError):
            graph.write("x", format="_not_a_real_format_xyz")
