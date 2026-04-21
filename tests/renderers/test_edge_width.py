"""Tests for the shared edge-width helper."""

from __future__ import annotations

import math

from crategraph.core.models import Relationship
from crategraph.renderers._edge_width import resolve_edge_widths


def _rel(src: str, tgt: str, **props) -> Relationship:
    return Relationship(source=src, target=tgt, type="r", properties=props)


class TestNone:
    def test_none_returns_none(self):
        assert resolve_edge_widths([_rel("a", "b")], None) is None

    def test_none_returns_none_on_empty(self):
        assert resolve_edge_widths([], None) is None


class TestScalar:
    def test_int_scalar_applied_to_every_edge(self):
        rels = [_rel("a", "b"), _rel("b", "c"), _rel("c", "a")]
        assert resolve_edge_widths(rels, 3) == [3.0, 3.0, 3.0]

    def test_float_scalar_applied_to_every_edge(self):
        rels = [_rel("a", "b"), _rel("b", "c")]
        assert resolve_edge_widths(rels, 2.5) == [2.5, 2.5]

    def test_scalar_on_empty_relationships_returns_empty_list(self):
        assert resolve_edge_widths([], 3) == []

    def test_zero_scalar_returns_zeros(self):
        assert resolve_edge_widths([_rel("a", "b")], 0) == [0.0]


class TestAttribute:
    def test_numeric_weight_uses_log1p_formula(self):
        rels = [
            _rel("a", "b", weight=1),
            _rel("b", "c", weight=10),
            _rel("c", "a", weight=100),
        ]
        widths = resolve_edge_widths(rels, "weight")
        assert widths == [
            1.0 + 2.0 * math.log1p(1),
            1.0 + 2.0 * math.log1p(10),
            1.0 + 2.0 * math.log1p(100),
        ]

    def test_missing_attribute_falls_back_to_one(self):
        rels = [_rel("a", "b")]
        assert resolve_edge_widths(rels, "weight") == [1.0]

    def test_nonexistent_attribute_on_all_edges_returns_all_ones(self):
        rels = [_rel("a", "b", weight=5), _rel("b", "c", weight=10)]
        assert resolve_edge_widths(rels, "frequency") == [1.0, 1.0]

    def test_non_numeric_attribute_falls_back_to_one(self):
        rels = [_rel("a", "b", weight="heavy")]
        assert resolve_edge_widths(rels, "weight") == [1.0]

    def test_none_attribute_value_falls_back_to_one(self):
        rels = [_rel("a", "b", weight=None)]
        assert resolve_edge_widths(rels, "weight") == [1.0]

    def test_negative_attribute_falls_back_to_one(self):
        rels = [_rel("a", "b", weight=-5)]
        assert resolve_edge_widths(rels, "weight") == [1.0]

    def test_zero_attribute_falls_back_to_one(self):
        rels = [_rel("a", "b", weight=0)]
        assert resolve_edge_widths(rels, "weight") == [1.0]

    def test_bool_true_falls_back_to_one(self):
        """bool is a subclass of int in Python — without explicit exclusion,
        True would encode as 1 + 2*log1p(1) ≈ 2.39. This regression test
        locks the fallback so `edge_width='bidirectional'` stays inert."""
        rels = [_rel("a", "b", bidirectional=True)]
        assert resolve_edge_widths(rels, "bidirectional") == [1.0]

    def test_bool_false_falls_back_to_one(self):
        rels = [_rel("a", "b", bidirectional=False)]
        assert resolve_edge_widths(rels, "bidirectional") == [1.0]

    def test_mixed_presence_within_graph(self):
        rels = [
            _rel("a", "b", weight=4),
            _rel("b", "c"),
            _rel("c", "a", weight=1),
        ]
        widths = resolve_edge_widths(rels, "weight")
        assert widths == [
            1.0 + 2.0 * math.log1p(4),
            1.0,
            1.0 + 2.0 * math.log1p(1),
        ]
