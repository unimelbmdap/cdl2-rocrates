import json
import random
import time
from itertools import chain
from pathlib import Path

import pytest

pytest.importorskip("rdflib")
pytest.importorskip("validators")

from crategraph.validators.masp.document import Node
from crategraph.validators.masp.profile import (
    ClassRule,
    ItemListRule,
    Profile,
    PropertyRule,
    PropertyValueRule,
)
from tests.validators.masp.conftest import make_profile

UPSTREAM = Path(__file__).parents[2] / "fixtures" / "masp" / "upstream"
REAL_PROFILES = (
    "ro-crate",
    "ro-crate-2",
    "ro-crate-masp",
    "ldac",
    "ldac-dmlex",
    "workflow",
    "software",
)
VOCABULARY_ROLE = "http://www.w3.org/ns/dx/prof/role/vocabulary"
INDICATOR_ROLE = "https://w3id.org/ro/conformance-indicators"


def parse(*rules, **kw) -> Profile:
    return Profile.from_json(make_profile(*rules, **kw), source="profile.json")


def add_resource(data: dict, descriptor: dict, *entities: dict) -> dict:
    """Append a ResourceDescriptor (and its entities) to the profile root's hasResource."""
    root = next(e for e in data["@graph"] if e["@id"] == "./")
    root.setdefault("hasResource", []).append({"@id": descriptor["@id"]})
    data["@graph"].extend([descriptor, *entities])
    return data


def with_root_id(data: dict, root_id: str) -> dict:
    """Give the profile root an absolute @id (and point the descriptor at it)."""
    for entity in data["@graph"]:
        if entity["@id"] == "./":
            entity["@id"] = root_id
        elif entity["@id"] == "ro-crate-metadata.json":
            entity["about"] = {"@id": root_id}
    return data


def profile_warnings(profile: Profile) -> list[dict]:
    return [w for w in profile.warnings if w["rule"] == "profile"]


def test_rules_classified_by_type():
    p = parse(
        {"@id": "#C", "@type": "rdfs:Class"},
        {"@id": "#p", "@type": "rdf:Property", "rdfs:label": "name"},
        {"@id": "#list", "@type": "ItemList", "itemListElement": [{"@id": "#x"}]},
        {"@id": "#pv", "@type": "PropertyValue", "value": "fixed"},
        {"@id": "#terms", "@type": "DefinedTermSet"},
        {"@id": "#x", "@type": "DefinedTerm"},
        # Expanded IRIs count too.
        {"@id": "#C2", "@type": "http://www.w3.org/2000/01/rdf-schema#Class"},
    )
    assert list(p.classes) == ["#C", "#C2"]
    assert isinstance(p.classes["#C"], ClassRule)
    assert list(p.properties) == ["#p"] and isinstance(p.properties["#p"], PropertyRule)
    assert list(p.item_lists) == ["#list"] and isinstance(p.item_lists["#list"], ItemListRule)
    assert p.item_lists["#list"].elements == (p.document.get("#x"),)
    assert isinstance(p.item_lists["#list"].elements[0], Node)
    assert list(p.property_values) == ["#pv"]
    assert p.property_values["#pv"] == PropertyValueRule(
        id="#pv", values=("fixed",), min_count=0, max_count=None
    )
    assert p.warnings == []


def test_class_types_default_to_own_id_and_expand():
    p = parse(
        {"@id": "Dataset", "@type": "rdfs:Class", "name": "Data"},
        {
            "@id": "#Root",
            "@type": "rdfs:Class",
            "rdfs:label": "Root",
            "prov:specializationOf": [{"@id": "Dataset"}, {"@id": "https://schema.org/Thing"}],
        },
        {"@id": "#Local", "@type": "rdfs:Class", "prov:specializationOf": {"@id": "ex:Thing"}},
    )
    assert p.classes["Dataset"].type_iris == {"http://schema.org/Dataset"}
    assert p.classes["Dataset"].name == "Data"
    assert p.classes["#Root"].type_iris == {"http://schema.org/Dataset", "http://schema.org/Thing"}
    assert p.classes["#Root"].name == "Root"
    # An undefined prefix does not expand, so the raw id is kept.
    assert p.classes["#Local"].type_iris == {"ex:Thing"}
    assert p.classes["#Local"].name == "#Local"
    assert p.warnings == []


def test_explicit_empty_specialization_warns_and_has_no_types():
    p = parse({"@id": "#Empty", "@type": "rdfs:Class", "prov:specializationOf": []})
    assert p.classes["#Empty"].type_iris == frozenset()
    assert p.warnings == [
        {
            "severity": "warning",
            "passed": False,
            "rule": "profile",
            "entity_id": "#Empty",
            "property": None,
            "message": "Class rule #Empty does not specify any types via prov:specializationOf",
            "source": "profile.json",
        }
    ]


def test_count_parsing_policy():
    good = [1, "2", 3.0, " 4 ", {"@value": 5}]
    bad = [-1, 1.5, "x", True, "-2"]
    rules = [
        {"@id": f"#good{i}", "@type": "rdf:Property", "name": "p", "sh:minCount": v}
        for i, v in enumerate(good)
    ] + [
        {"@id": f"#bad{i}", "@type": "rdf:Property", "name": "p", "sh:maxCount": v}
        for i, v in enumerate(bad)
    ]
    p = parse(*rules)
    assert [p.properties[f"#good{i}"].min_count for i in range(len(good))] == [1, 2, 3, 4, 5]
    assert all(p.properties[f"#bad{i}"].max_count is None for i in range(len(bad)))
    assert [w["message"] for w in p.warnings] == [
        f"Rule #bad{i}: ignoring invalid sh:maxCount {v!r}" for i, v in enumerate(bad)
    ]
    assert [w["entity_id"] for w in p.warnings] == [f"#bad{i}" for i in range(len(bad))]
    assert {w["rule"] for w in p.warnings} == {"profile"}


def test_count_policy_applies_to_class_and_property_value_rules():
    p = parse(
        {"@id": "#C", "@type": "rdfs:Class", "sh:minCount": "x"},
        {"@id": "#pv", "@type": "PropertyValue", "sh:maxCount": 1.5, "sh:minCount": "1"},
    )
    assert p.classes["#C"].min_count == 0
    assert (p.property_values["#pv"].min_count, p.property_values["#pv"].max_count) == (1, None)
    assert [w["message"] for w in p.warnings] == [
        "Rule #C: ignoring invalid sh:minCount 'x'",
        "Rule #pv: ignoring invalid sh:maxCount 1.5",
    ]


def test_counts_and_unbounded_max():
    p = parse(
        {"@id": "#C", "@type": "rdfs:Class", "sh:minCount": 1, "sh:maxCount": 1},
        {"@id": "#D", "@type": "rdfs:Class"},
        {
            "@id": "#p",
            "@type": "rdf:Property",
            "name": "x",
            "sh:minCount": [2, 9],
            "sh:maxCount": 0,
        },
    )
    assert (p.classes["#C"].min_count, p.classes["#C"].max_count) == (1, 1)
    assert (p.classes["#D"].min_count, p.classes["#D"].max_count) == (0, None)
    # The first value wins; an explicit 0 maximum stays 0.
    assert (p.properties["#p"].min_count, p.properties["#p"].max_count) == (2, 0)


def test_property_rule_fields():
    p = parse(
        {
            "@id": "#prop_license",
            "@type": "rdf:Property",
            "name": "License",
            "rdfs:label": "license",
            "rangeIncludes": [{"@id": "CreativeWork"}, "URL"],
            "domainIncludes": {"@id": "#Root"},
        },
        {"@id": "#prop_id", "@type": "rdf:Property", "rdfs:label": "@id"},
        {"@id": "#prop_unknown", "@type": "rdf:Property", "name": "ex:thing"},
        {
            "@id": "#prop_fallback",
            "@type": "rdf:Property",
            "name": "author",
            "http://schema.org/rangeIncludes": {"@id": "Person"},
        },
    )
    lic = p.properties["#prop_license"]
    assert (lic.name, lic.iri, lic.label) == ("license", "http://schema.org/license", "License")
    assert lic.ranges == ("CreativeWork", "URL") and lic.domains == ("#Root",)
    assert (lic.min_count, lic.max_count) == (0, None)
    assert p.properties["#prop_id"].iri is None
    assert p.properties["#prop_id"].label == "@id"
    assert p.properties["#prop_unknown"].iri == "ex:thing"
    assert p.properties["#prop_fallback"].ranges == ("Person",)


def test_inherited_property_rules_follow_subclass_chain():
    p = parse(
        {"@id": "#A", "@type": "rdfs:Class"},
        {"@id": "#B", "@type": "rdfs:Class", "rdfs:subClassOf": {"@id": "#A"}},
        {"@id": "#C", "@type": "rdfs:Class", "rdfs:subClassOf": {"@id": "#B"}},
        {"@id": "#a1", "@type": "rdf:Property", "name": "a1", "domainIncludes": {"@id": "#A"}},
        {"@id": "#b1", "@type": "rdf:Property", "name": "b1", "domainIncludes": {"@id": "#B"}},
        {
            "@id": "#shared",
            "@type": "rdf:Property",
            "name": "shared",
            "domainIncludes": [{"@id": "#A"}, {"@id": "#C"}],
        },
        {"@id": "#c1", "@type": "rdf:Property", "name": "c1", "domainIncludes": {"@id": "#C"}},
    )
    assert p.ancestor_class_ids("#C") == ["#B", "#A"]
    ids = [r.id for r in p.classes["#C"].property_rules]
    assert ids == ["#shared", "#c1", "#b1", "#a1"]
    assert [r.id for r in p.classes["#B"].property_rules] == ["#b1", "#a1", "#shared"]
    assert [r.id for r in p.classes["#A"].property_rules] == ["#a1", "#shared"]
    assert p.classes["#C"].property_rules[1] is p.properties["#c1"]


def test_ancestors_absent_from_the_profile_contribute_no_property_rules():
    # JS l.303-308: getEntity(ancestorId) is null for an ancestor the profile
    # does not describe, so its domainIncludes members are never collected.
    rules = (
        {
            "@id": "#C",
            "@type": "rdfs:Class",
            "rdfs:subClassOf": {"@id": "https://schema.org/Thing"},
        },
        {"@id": "#c1", "@type": "rdf:Property", "name": "c1", "domainIncludes": {"@id": "#C"}},
        {
            "@id": "#t1",
            "@type": "rdf:Property",
            "name": "t1",
            "domainIncludes": {"@id": "https://schema.org/Thing"},
        },
    )
    absent = parse(*rules)
    assert absent.ancestor_class_ids("#C") == ["https://schema.org/Thing"]
    assert [r.id for r in absent.classes["#C"].property_rules] == ["#c1"]
    present = parse(*rules, {"@id": "https://schema.org/Thing", "@type": "rdfs:Class"})
    assert [r.id for r in present.classes["#C"].property_rules] == ["#c1", "#t1"]


def test_property_rules_include_entities_outside_the_schema_descriptor():
    # The JS builds a property rule from every entity whose domainIncludes
    # names the class, listed in the schema descriptor or not.
    data = make_profile({"@id": "#C", "@type": "rdfs:Class"})
    data["@graph"].append(
        {"@id": "#loose", "@type": "rdf:Property", "name": "x", "domainIncludes": {"@id": "#C"}}
    )
    p = Profile.from_json(data, source="profile.json")
    assert "#loose" not in p.properties
    assert [r.id for r in p.classes["#C"].property_rules] == ["#loose"]


def test_ancestor_ids_survive_cycles():
    p = parse(
        {"@id": "#C", "@type": "rdfs:Class", "rdfs:subClassOf": [{"@id": "#B"}, {"@id": "#D"}]},
        {"@id": "#B", "@type": "rdfs:Class", "rdfs:subClassOf": {"@id": "#A"}},
        {"@id": "#A", "@type": "rdfs:Class", "rdfs:subClassOf": {"@id": "#B"}},
        {"@id": "#D", "@type": "rdfs:Class", "rdfs:subClassOf": "#E"},
        {"@id": "#E", "@type": "rdfs:Class"},
        {"@id": "#Self", "@type": "rdfs:Class", "rdfs:subClassOf": {"@id": "#Self"}},
    )
    # As in the JS (parentClasses, l.1560-1576), a path that runs into a cycle
    # yields nothing, so only the acyclic branch through #D survives.
    assert p.ancestor_class_ids("#C") == ["#D", "#E"]
    assert p.ancestor_class_ids("#A") == []
    assert p.ancestor_class_ids("#Self") == []
    assert p.ancestor_class_ids("#missing") == []
    assert p.classes["#A"].property_rules == ()


def test_overly_deep_class_hierarchy_raises_value_error():
    chain_ = [{"@id": "#c0", "@type": "rdfs:Class"}]
    chain_ += [
        {"@id": f"#c{i}", "@type": "rdfs:Class", "rdfs:subClassOf": {"@id": f"#c{i - 1}"}}
        for i in range(1, 1100)
    ]
    for declared in (chain_, chain_[::-1]):
        with pytest.raises(ValueError, match="more than 100 classes deep"):
            parse(*declared)


def _chain(length: int) -> list[dict]:
    classes = [{"@id": "#c0", "@type": "rdfs:Class"}]
    classes += [
        {"@id": f"#c{i}", "@type": "rdfs:Class", "rdfs:subClassOf": {"@id": f"#c{i - 1}"}}
        for i in range(1, length)
    ]
    return classes


def test_class_depth_limit_counts_classes():
    assert len(parse(*_chain(100)).ancestor_class_ids("#c99")) == 99
    with pytest.raises(ValueError, match="more than 100 classes deep"):
        parse(*_chain(101))


def test_many_unrelated_classes_are_not_mistaken_for_tangled_cycles():
    profile = parse(*[{"@id": f"#c{i}", "@type": "rdfs:Class"} for i in range(10_001)])
    assert len(profile.classes) == 10_001


def test_long_class_cycle_raises_value_error():
    size = 1100
    ring = [
        {"@id": f"#c{i}", "@type": "rdfs:Class", "rdfs:subClassOf": {"@id": f"#c{(i + 1) % size}"}}
        for i in range(size)
    ]
    with pytest.raises(ValueError, match="more than 100 classes deep"):
        parse(*ring)


def test_densely_cyclic_class_hierarchy_raises_value_error():
    size = 20
    classes = [
        {
            "@id": f"#c{i}",
            "@type": "rdfs:Class",
            "rdfs:subClassOf": [{"@id": f"#c{j}"} for j in range(size) if j != i],
        }
        for i in range(size)
    ]
    start = time.perf_counter()
    with pytest.raises(ValueError, match="too tangled"):
        parse(*classes)
    assert time.perf_counter() - start < 10


def _enumerated_ancestors(profile: Profile, class_id: str) -> list[str]:
    """The original path-enumerating algorithm (JS ``parentClasses``), kept as an oracle."""

    def paths(current: str, visited: frozenset[str]) -> list[list[str]]:
        if current in visited:
            return []
        visited = visited | {current}
        parents = profile._parent_class_ids(current)
        if not parents:
            return [[]]
        return [[parent, *sub] for parent in parents for sub in paths(parent, visited)]

    return list(dict.fromkeys(chain.from_iterable(paths(class_id, frozenset()))))


def _random_hierarchy(rng: random.Random) -> list[dict]:
    size = rng.randint(1, 7)
    ids = [f"#{i}" for i in range(size)]
    targets = [*ids, "#undeclared", "https://schema.org/Enumeration"]
    classes = []
    for class_id in ids:
        parents = [{"@id": rng.choice(targets)} for _ in range(rng.choice((0, 1, 1, 2, 2, 3)))]
        entity = {"@id": class_id, "@type": "rdfs:Class"}
        if parents:
            entity["rdfs:subClassOf"] = parents if len(parents) > 1 else parents[0]
        classes.append(entity)
    return classes


def test_ancestor_ids_match_path_enumeration_on_random_hierarchies():
    rng = random.Random(20261021)
    for _ in range(200):
        classes = _random_hierarchy(rng)
        p = parse(*classes)
        queries = [c["@id"] for c in classes] + ["#undeclared"]
        rng.shuffle(queries)  # the memo must not depend on query order
        for class_id in queries:
            expected = _enumerated_ancestors(p, class_id)
            assert p.ancestor_class_ids(class_id) == expected, (classes, class_id)


def test_layered_diamond_ancestors_are_fast():
    # 18 layers of 2 classes, each a subclass of both classes in the layer
    # above: 131,072 paths from the bottom, which the old enumeration walked.
    layers = 18
    classes = []
    for layer in range(layers):
        for side in "ab":
            entity = {"@id": f"#L{layer}{side}", "@type": "rdfs:Class"}
            if layer + 1 < layers:
                entity["rdfs:subClassOf"] = [
                    {"@id": f"#L{layer + 1}a"},
                    {"@id": f"#L{layer + 1}b"},
                ]
            classes.append(entity)
    data = make_profile(*classes)
    start = time.perf_counter()
    p = Profile.from_json(data, source="profile.json")
    ancestors = p.ancestor_class_ids("#L0a")
    elapsed = time.perf_counter() - start
    assert len(ancestors) == 2 * (layers - 1)
    assert ancestors[:3] == ["#L1a", "#L2a", "#L3a"]
    assert elapsed < 0.1


def test_enumeration_detection_through_subclass_chain():
    p = parse(
        {"@id": "#Licence", "@type": "rdfs:Class", "rdfs:subClassOf": {"@id": "#Kind"}},
        {
            "@id": "#Kind",
            "@type": "rdfs:Class",
            "rdfs:subClassOf": {"@id": "https://schema.org/Enumeration"},
        },
        {
            "@id": "#OldStyle",
            "@type": "rdfs:Class",
            "rdfs:subClassOf": {"@id": "http://schema.org/Enumeration"},
        },
        {"@id": "#Plain", "@type": "rdfs:Class"},
    )
    assert p.is_enumeration_class("#Licence")
    assert p.is_enumeration_class("#Kind")
    assert p.is_enumeration_class("#OldStyle")
    assert p.is_enumeration_class("https://schema.org/Enumeration")
    assert p.is_enumeration_class("http://schema.org/Enumeration")
    assert not p.is_enumeration_class("#Plain")
    assert not p.is_enumeration_class("#missing")


def test_enumeration_values_from_vocabulary_descriptor():
    data = make_profile(
        {"@id": "#Kind", "@type": "rdfs:Class"},
        {"@id": "#Colour", "@type": "rdfs:Class"},
    )
    data["@graph"].extend(
        [
            {"@id": "#k-in-vocab", "@type": "#Kind"},
            {"@id": "#k-outside", "@type": "#Kind"},
            {"@id": "#red", "@type": ["DefinedTerm", "#Colour"]},
            {"@id": "#blue", "@type": "#Colour"},
        ]
    )
    vocabulary = {
        "@id": "#vocab",
        "@type": "ResourceDescriptor",
        "hasRole": {"@id": VOCABULARY_ROLE},
        "hasPart": [{"@id": "#k-in-vocab"}],
    }
    p = Profile.from_json(add_resource(data, vocabulary), source="profile.json")
    # The vocabulary descriptor wins for a type it lists ...
    assert p.enumeration_value_ids("#Kind") == {"#k-in-vocab"}
    # ... otherwise every profile entity typed with the class counts.
    assert p.enumeration_value_ids("#Colour") == {"#red", "#blue"}
    assert p.enumeration_value_ids("#Nothing") == frozenset()


def test_has_part_as_json_string():
    data = make_profile()
    data["@graph"].extend(
        [
            {"@id": "#C", "@type": "rdfs:Class"},
            {"@id": "#p", "@type": "rdf:Property", "name": "x"},
        ]
    )
    descriptor = next(e for e in data["@graph"] if e["@id"] == "#profile-descriptor")
    descriptor["hasPart"] = json.dumps([{"@id": "#C"}, {"@id": "#p"}])
    p = Profile.from_json(data, source="profile.json")
    assert list(p.classes) == ["#C"] and list(p.properties) == ["#p"]


def test_has_part_plain_string_ids_resolve():
    data = make_profile()
    data["@graph"].append({"@id": "#C", "@type": "rdfs:Class"})
    descriptor = next(e for e in data["@graph"] if e["@id"] == "#profile-descriptor")
    descriptor["hasPart"] = ["#C"]
    assert list(Profile.from_json(data, source="profile.json").classes) == ["#C"]


def test_property_rule_without_name_warns_once():
    p = parse(
        {"@id": "#A", "@type": "rdfs:Class"},
        {"@id": "#B", "@type": "rdfs:Class", "rdfs:subClassOf": {"@id": "#A"}},
        {"@id": "#nameless", "@type": "rdf:Property", "domainIncludes": {"@id": "#A"}},
    )
    assert p.properties["#nameless"].name is None
    assert p.properties["#nameless"].iri is None
    assert p.properties["#nameless"].label == "#nameless"
    assert p.warnings == [
        {
            "severity": "warning",
            "passed": False,
            "rule": "profile",
            "entity_id": "#nameless",
            "property": None,
            "message": "Property rule #nameless does not have a name",
            "source": "profile.json",
        }
    ]


def test_profile_with_unresolved_context_still_parses():
    ctx = ["https://example.org/unknown-context.jsonld", {"ex": "http://example.org/terms#"}]
    p = parse(
        {"@id": "#C", "@type": "rdfs:Class", "prov:specializationOf": {"@id": "Dataset"}},
        {"@id": "#p", "@type": "rdf:Property", "name": "license", "domainIncludes": {"@id": "#C"}},
        context=ctx,
    )
    # Structural keys are read as written, so the rules still parse ...
    assert list(p.classes) == ["#C"] and list(p.properties) == ["#p"]
    assert [r.id for r in p.classes["#C"].property_rules] == ["#p"]
    # ... but terms the context would have defined fall back to raw strings.
    assert p.classes["#C"].type_iris == {"Dataset"}
    assert p.properties["#p"].iri is None
    assert p.warnings == [
        {
            "severity": "warning",
            "passed": False,
            "rule": "context",
            "entity_id": None,
            "property": None,
            "message": (
                "Profile context https://example.org/unknown-context.jsonld could not be "
                "resolved; terms it defines are compared as written"
            ),
            "source": "profile.json",
        }
    ]


def test_missing_root_or_schema_descriptor_raises():
    data = make_profile()
    data["@graph"] = [e for e in data["@graph"] if e["@id"] != "ro-crate-metadata.json"]
    with pytest.raises(ValueError, match="root"):
        Profile.from_json(data, source="profile.json")
    data = make_profile()
    descriptor = next(e for e in data["@graph"] if e["@id"] == "#profile-descriptor")
    descriptor["hasRole"] = {"@id": VOCABULARY_ROLE}
    with pytest.raises(ValueError, match="schema"):
        Profile.from_json(data, source="profile.json")


def test_accepted_conformance_uris_from_indicator_list():
    data = make_profile()
    indicators = {
        "@id": "#hasConformanceIndicators",
        "@type": "ResourceDescriptor",
        "hasRole": {"@id": INDICATOR_ROLE},
        "hasArtifact": [{"@id": "#indicators"}, {"@id": "https://example.org/direct"}],
    }
    item_list = {
        "@id": "#indicators",
        "@type": "ItemList",
        "itemListElement": [
            {"@id": "https://example.org/profile/1.0"},
            "https://example.org/profile",
            {"@id": "https://example.org/profile/1.0"},
        ],
    }
    p = Profile.from_json(add_resource(data, indicators, item_list), source="profile.json")
    assert p.accepted_conformance_uris() == (
        "https://example.org/profile/1.0",
        "https://example.org/profile",
        "https://example.org/direct",
    )


def test_accepted_conformance_uris_fall_back_to_profile_entity():
    # A conformsTo item list naming a Profile entity wins over the root.
    data = make_profile(
        {
            "@id": "#conformsTo-values",
            "@type": "ItemList",
            "itemListElement": [{"@id": "#not-a-profile"}, {"@id": "https://example.org/p"}],
        },
        {"@id": "#not-a-profile", "@type": "CreativeWork"},
        {"@id": "https://example.org/p", "@type": "Profile"},
    )
    p = Profile.from_json(with_root_id(data, "https://example.org/root"), source="profile.json")
    assert p.accepted_conformance_uris() == ("https://example.org/p",)


def test_accepted_conformance_uris_fall_back_to_root():
    data = with_root_id(make_profile(), "https://example.org/root")
    p = Profile.from_json(data, source="profile.json")
    assert p.accepted_conformance_uris() == ("https://example.org/root",)
    # A relative root id (and no other Profile entity) gives nothing.
    assert parse().accepted_conformance_uris() == ()


def test_load_reads_a_file(tmp_path):
    path = tmp_path / "ro-crate-metadata.json"
    path.write_text(json.dumps(make_profile({"@id": "#C", "@type": "rdfs:Class"})))
    p = Profile.load(path)
    assert p.source == str(path) and p.document.source == str(path)
    assert list(p.classes) == ["#C"]


@pytest.mark.parametrize("name", REAL_PROFILES)
def test_real_profiles_parse_without_error(name):
    p = Profile.load(UPSTREAM / name / "ro-crate-metadata.json")
    assert p.classes
    assert profile_warnings(p) == []
    assert [w for w in p.warnings if w["rule"] == "context"] == []
    assert p.accepted_conformance_uris()
