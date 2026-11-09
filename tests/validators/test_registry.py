"""Tests for the validator registry and Graph.validate."""

from __future__ import annotations

import re
import subprocess
import sys

import pytest

from crategraph.core.interfaces import Validator
from crategraph.validators import (
    _REGISTRY,
    UnknownValidatorError,
    get_validator,
    list_kinds,
    register_validator,
)
from crategraph.validators._extra import require_validate_extra
from crategraph.validators.report import ValidationReport


@pytest.fixture
def clean_registry():
    before = dict(_REGISTRY)
    yield
    _REGISTRY.clear()
    _REGISTRY.update(before)


def test_get_unknown_kind_raises_listing_known():
    with pytest.raises(UnknownValidatorError, match=r"Known kinds: .*masp"):
        get_validator("nope")


def test_masp_is_registered():
    assert "masp" in list_kinds()


def test_graph_validate_dispatches_kind_and_passes_profile_and_kwargs(
    people_graph, clean_registry
):
    seen = {}

    class Dummy(Validator):
        def __init__(self, profile, **kw):
            seen.update(profile=profile, **kw)

        def validate(self, graph):
            return ValidationReport()

    register_validator("dummy", Dummy)
    report = people_graph.validate("p.json", kind="dummy", flag=True)
    assert isinstance(report, ValidationReport)
    assert seen == {"profile": "p.json", "flag": True}


def test_import_crategraph_validators_does_not_import_rdflib():
    code = (
        "import sys, crategraph; "
        "from crategraph.validators import MaspValidator, ValidationReport; "
        "assert not {'rdflib', 'regex', 'validators'} & set(sys.modules)"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


@pytest.mark.parametrize("missing", ["rdflib", "regex", "validators"])
def test_require_validate_extra_message(monkeypatch, missing):
    monkeypatch.setitem(sys.modules, missing, None)
    with pytest.raises(ImportError, match=re.escape('pip install "crategraph[validate]"')):
        require_validate_extra()
