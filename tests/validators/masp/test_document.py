import json

import pytest

pytest.importorskip("rdflib")
pytest.importorskip("validators")

from crategraph.validators.masp.document import (
    CrateDocument,
    is_reference,
    literal_of,
)
from tests.validators.masp.conftest import make_crate


def doc(*entities, **kw):
    return CrateDocument.from_json(make_crate(*entities, **kw), source="t.json")


def test_values_always_lists_and_keys_as_written():
    d = doc({"@id": "#a", "@type": "Person", "name": "A", "dct:x": [1, 2]})
    n = d.get("#a")
    assert n.properties == {"name": ["A"], "dct:x": [1, 2]}
    assert "@id" not in n.properties and "@type" not in n.properties


def test_duplicate_ids_merge_and_are_reported():
    d = doc(
        {"@id": "#a", "@type": "Person", "name": "A"},
        {"@id": "#a", "@type": ["Person", "Thing"], "name": "B"},
        {"name": "no id"},
    )
    n = d.get("#a")
    assert n.types == ("Person", "Thing")
    assert n.properties["name"] == ["A", "B"]
    assert d.duplicate_ids == ("#a",)


def test_missing_type_and_string_type():
    d = doc({"@id": "#a"}, {"@id": "#b", "@type": "Person"})
    assert d.get("#a").types == ()
    assert d.get("#b").types == ("Person",)


def test_type_iris_expand_with_crate_context():
    d = doc(
        {"@id": "#a", "@type": "Dataset"},
        {"@id": "#b", "@type": "https://schema.org/Dataset"},
    )
    assert d.type_iris(d.get("#a")) == {"http://schema.org/Dataset"}
    assert d.type_iris(d.get("#b")) == {"http://schema.org/Dataset"}


def test_values_for_matches_by_iri_across_spellings():
    ctx = [
        "https://w3id.org/ro/crate/1.2/context",
        {
            "@vocab": "http://schema.org/",
            "rightsHolder": "dct:rightsHolder",
            "dct": "http://purl.org/dc/terms/",
        },
    ]
    d = doc({"@id": "#a", "rightsHolder": {"@id": "#p"}}, context=ctx)
    n = d.get("#a")
    got = d.values_for(n, "dct:rightsHolder", "http://purl.org/dc/terms/rightsHolder")
    assert got == [{"@id": "#p"}]
    assert d.values_for(n, "nope", "http://purl.org/dc/terms/nope") is None
    assert d.values_for(n, "rightsHolder", None) == [{"@id": "#p"}]


def test_values_for_at_id():
    d = doc({"@id": "#a"})
    assert d.values_for(d.get("#a"), "@id", None) == ["#a"]


def test_root_and_descriptor():
    d = doc({"@id": "#a"})
    assert d.descriptor().id == "ro-crate-metadata.json"
    assert d.root().id == "./"
    empty = CrateDocument.from_json({"@graph": []}, source="e")
    assert empty.root() is None and empty.descriptor() is None


def test_no_context_falls_back_to_raw_types():
    d = CrateDocument.from_json(
        {"@graph": [{"@id": "#a", "@type": "Thing", "name": "x"}]}, source="n"
    )
    assert d.type_iris(d.get("#a")) == {"Thing"}
    assert d.values_for(d.get("#a"), "name", None) == ["x"]


def test_load_invalid_json_raises_value_error_naming_file(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{nope")
    with pytest.raises(ValueError, match=r"bad\.json"):
        CrateDocument.load(p)
    q = tmp_path / "nograph.json"
    q.write_text(json.dumps({"@context": []}))
    with pytest.raises(ValueError, match=r"nograph\.json"):
        CrateDocument.load(q)


def test_literal_of_value_object():
    assert literal_of({"@value": "x", "@language": "en"}) == "x"
    assert literal_of("y") == "y"
    assert is_reference({"@id": "#a"}) and not is_reference("#a")


@pytest.mark.parametrize(
    "bad_context",
    [
        [{"@vocab": "http://schema.org/"}, {"@vocab": 5}],
        {"@vocab": 5},
        {"foo": {"@id": 5}},
        {"@base": 5},
    ],
)
def test_malformed_context_raises_value_error_naming_source(bad_context):
    data = make_crate(context=bad_context)
    with pytest.raises(ValueError, match=r"t\.json: unusable @context"):
        CrateDocument.from_json(data, source="t.json")


@pytest.mark.parametrize("bad_context", [["https://w3id.org/ro/crate/1.1/context", 5], True])
def test_non_string_context_item_is_reported_as_unresolved(bad_context):
    d = CrateDocument.from_json(make_crate(context=bad_context), source="t.json")
    assert d.unresolved_contexts[-1] in ("5", "True")


def test_load_missing_file_stays_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        CrateDocument.load(tmp_path / "nope.json")


def test_load_undecodable_file_raises_value_error_naming_path(tmp_path):
    path = tmp_path / "ro-crate-metadata.json"
    path.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(ValueError, match=r"ro-crate-metadata\.json: cannot read file"):
        CrateDocument.load(path)


def test_load_directory_raises_value_error_naming_path(tmp_path):
    with pytest.raises(ValueError, match="cannot read file"):
        CrateDocument.load(tmp_path)
