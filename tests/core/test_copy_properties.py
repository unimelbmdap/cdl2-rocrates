"""Deepcopy-equivalence tests for models._copy_properties and the scoped
copy inside Graph.to_networkx(copy=True)."""

from __future__ import annotations

import copy
import dataclasses
from datetime import date

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship, _copy_properties


class TestCopyProperties:
    def test_nested_detachment(self):
        original = {"a": {"b": [1, 2, {"c": "deep"}]}, "t": (1, [2])}
        copied = _copy_properties(original)
        copied["a"]["b"][2]["c"] = "mutated"
        copied["t"][1].append(3)
        assert original["a"]["b"][2]["c"] == "deep"
        assert original["t"][1] == [2]

    def test_scalars_pass_through(self):
        original = {"s": "x", "i": 1, "f": 1.5, "b": True, "n": None}
        assert _copy_properties(original) == original

    def test_alias_preservation_containers(self):
        shared = [1, 2]
        copied = _copy_properties({"a": shared, "b": shared})
        assert copied["a"] is copied["b"]
        assert copied["a"] is not shared

    def test_alias_preservation_exotic_objects(self):
        """The deepcopy fallback shares the memo, so exotic-object aliasing
        survives too."""

        class Marker:
            pass

        shared = Marker()
        copied = _copy_properties({"a": shared, "b": shared})
        assert copied["a"] is copied["b"]
        assert copied["a"] is not shared

    def test_exotic_value_deepcopied_not_shared(self):
        d = date(2026, 7, 5)
        holder = {"when": [d]}
        copied = _copy_properties(holder)
        assert copied["when"][0] == d
        # date is immutable so identity MAY be preserved (deepcopy returns
        # atomic immutables as-is); the guarantee is detachment of the
        # containers around it:
        copied["when"].append("extra")
        assert holder["when"] == [d]

    def test_cycle_terminates(self):
        d: dict = {"name": "loop"}
        d["self"] = d
        copied = _copy_properties(d)
        assert copied["self"] is copied
        assert copied is not d

    def test_tuple_cycle_matches_deepcopy(self):
        """tuple -> list -> same tuple: handled by the deepcopy fallback
        with the shared memo, preserving the cyclic object graph."""
        inner: list = []
        outer = (inner,)
        inner.append(outer)
        copied = _copy_properties({"cycle": outer})
        assert copied["cycle"][0][0] is copied["cycle"]

    def test_dict_subclass_type_preserved(self):
        """Container subclasses take the deepcopy fallback so their concrete
        type survives, matching deepcopy."""

        class MyDict(dict):
            pass

        original = {"d": MyDict(a=1)}
        copied = _copy_properties(original)
        assert type(copied["d"]) is MyDict
        assert copied["d"] == {"a": 1}
        assert copied["d"] is not original["d"]

    def test_matches_deepcopy_on_jsonld_shape(self):
        original = {
            "@id": "#x",
            "name": ["A", "B"],
            "nested": {"@id": "#y", "vals": [1, {"k": None}]},
        }
        assert _copy_properties(original) == copy.deepcopy(original)


class TestReplaceParity:
    def test_entity_replace_matches_deepcopy(self):
        entity = Entity(
            id="#e",
            types=["Person", "Author"],  # list input exercises __post_init__
            properties={"name": "X", "tags": ["a"]},
            source="/data/crates/alpha",
        )
        via_deepcopy = copy.deepcopy(entity)
        via_replace = dataclasses.replace(entity, properties=_copy_properties(entity.properties))
        assert via_replace == via_deepcopy
        assert via_replace.types == via_deepcopy.types == ("Person", "Author")
        assert repr(via_replace) == repr(via_deepcopy)
        assert via_replace.properties is not entity.properties

    def test_relationship_replace_matches_deepcopy(self):
        rel = Relationship(source="#a", target="#b", type="knows", properties={"since": [2001]})
        via_deepcopy = copy.deepcopy(rel)
        via_replace = dataclasses.replace(rel, properties=_copy_properties(rel.properties))
        assert via_replace == via_deepcopy
        assert repr(via_replace) == repr(via_deepcopy)


class TestToNetworkxScopedCopy:
    def test_nested_mutation_safety_preserved(self):
        g = Graph()
        g._add_node(Entity(id="#item", types=["Dataset"], properties={"tags": ["a", ["deep"]]}))
        nxg = g.to_networkx()
        nxg.nodes["#item"]["entity"].properties["tags"][1].append("mutated")
        assert g.entities[0].properties["tags"][1] == ["deep"]

    def test_copy_false_still_shares_objects(self):
        g = Graph()
        g._add_node(Entity(id="#item", types=["Dataset"], properties={"k": "v"}))
        nxg = g.to_networkx(copy=False)
        assert nxg.nodes["#item"]["entity"] is g.entities[0]

    def test_entity_valued_property_narrowed_contract(self):
        """Pin the deliberately narrowed contract for a pathological shape.

        No crategraph path puts Entity objects inside ``properties`` (values
        come from JSON-LD), but if a caller does, the scoped copy detaches
        that value as an independent deep copy rather than re-pointing it at
        the enclosing copied Entity the way whole-object deepcopy once did.
        Both entities stay detached from the source graph either way.
        """
        inner = Entity(id="#inner", types=["Person"], properties={"name": "X"})
        g = Graph()
        g._add_node(dataclasses.replace(inner, id="#outer", properties={"ref": inner}))
        g._add_node(inner)
        nxg = g.to_networkx()
        copied_ref = nxg.nodes["#outer"]["entity"].properties["ref"]
        assert copied_ref == inner
        assert copied_ref is not inner  # detached from the source graph
        assert copied_ref is not nxg.nodes["#inner"]["entity"]  # independent copy
