"""Shared fixtures for crategraph tests."""

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture
def people_graph():
    """The committed people-demo tutorial crate (8 entities, 12 relationships)."""
    from crategraph import Crate

    return Crate(_REPO_ROOT / "docs" / "tutorials" / "data" / "people-demo")
