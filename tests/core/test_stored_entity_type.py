"""Regression: Graph._entities stores only bare Entity, never EntityView.

Guards the internal/record boundary that the EntityView accessor flip
relies on — ingestion and derived-graph construction must never store a
view in ``_entities``.
"""

from __future__ import annotations

from pathlib import Path

from crategraph import Crate
from crategraph.core.models import Entity

FIXTURE = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


def test_entities_dict_holds_only_bare_entities_after_load() -> None:
    crate = Crate(str(FIXTURE))
    assert crate._entities, "fixture should load at least one entity"
    assert all(isinstance(e, Entity) for e in crate._entities.values())


def test_entities_dict_holds_only_bare_entities_after_filter() -> None:
    crate = Crate(str(FIXTURE))
    derived = crate.select(entity_types=["Person"])
    assert all(isinstance(e, Entity) for e in derived._entities.values())
