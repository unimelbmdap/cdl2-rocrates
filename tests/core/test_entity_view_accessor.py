"""Tests for Graph.entity_view."""

from __future__ import annotations

from pathlib import Path

import pytest

from crategraph import Crate
from crategraph.core.views import EntityView

FIXTURE = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


def test_entity_view_returns_graph_aware_view() -> None:
    g = Crate(str(FIXTURE))
    view = g.entity_view("#alice")
    assert isinstance(view, EntityView)
    assert view.id == "#alice"
    assert view.graph is g


def test_entity_view_unknown_id_raises() -> None:
    g = Crate(str(FIXTURE))
    with pytest.raises(ValueError, match="not in graph"):
        g.entity_view("#no-such-entity")
