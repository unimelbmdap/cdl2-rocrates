from collections import Counter

import pytest

pytest.importorskip("rdflib")
pytest.importorskip("validators")

from crategraph.validators.masp import engine
from crategraph.validators.masp.document import CrateDocument
from crategraph.validators.masp.engine import CardinalityOutcome, ValidationRun
from crategraph.validators.masp.profile import Profile
from crategraph.validators.report import ValidationReport
from tests.validators.masp.conftest import DEFAULT_CONTEXT, make_crate, make_profile


def cls(rule_id, types, *, name=None, min_count=None, max_count=None, **extra):
    rule = {"@id": rule_id, "@type": "rdfs:Class", "prov:specializationOf": types, **extra}
    if name is not None:
        rule["name"] = name
    if min_count is not None:
        rule["sh:minCount"] = min_count
    if max_count is not None:
        rule["sh:maxCount"] = max_count
    return rule


def prop(rule_id, label, domain, ranges=(), *, min_count=None, max_count=None):
    rule = {
        "@id": rule_id,
        "@type": "rdf:Property",
        "rdfs:label": label,
        "domainIncludes": {"@id": domain},
        "rangeIncludes": [{"@id": r} for r in ranges],
    }
    if min_count is not None:
        rule["sh:minCount"] = min_count
    if max_count is not None:
        rule["sh:maxCount"] = max_count
    return rule


def pv(rule_id, *values, min_count=None, max_count=None):
    rule = {"@id": rule_id, "@type": "PropertyValue", "value": list(values)}
    if min_count is not None:
        rule["sh:minCount"] = min_count
    if max_count is not None:
        rule["sh:maxCount"] = max_count
    return rule


def validate(rules, *entities, root=None, extra=(), profile_context=None, crate_context=None):
    """Run the engine; *extra* profile entities stay out of the schema descriptor."""
    data = make_profile(*rules, context=profile_context)
    data["@graph"].extend(extra)
    profile = Profile.from_json(data, source="profile.json")
    crate = CrateDocument.from_json(
        make_crate(*entities, root=root, context=crate_context), source="crate.json"
    )
    run = ValidationRun(profile, crate)
    return run, run.run()


def errors(rows):
    return [r for r in rows if not r["passed"] and r["severity"] == "error"]


def entity_rows(rows, entity_id):
    return [r for r in rows if r["entity_id"] == entity_id]


def only_row(rows, rule, entity_id, prop_name):
    found = [
        r
        for r in rows
        if r["rule"] == rule and r["entity_id"] == entity_id and r["property"] == prop_name
    ]
    assert len(found) == 1, found
    return found[0]


def valid_counts(run):
    return {c.class_id: c.valid_count for c in run.cardinalities}


ROOT_RULES = (
    cls("#Root", {"@id": "Dataset"}, name="Root Data Entity", min_count=1, max_count=1),
    prop("#license", "license", "#Root", min_count=1),
)


def test_cardinality_pass_and_min_failure_explains_near_miss():
    run, rows = validate(ROOT_RULES)
    [error] = errors(rows)
    assert error["rule"] == "#Root"
    assert error["entity_id"] is None and error["property"] is None
    assert error["source"] == "crate.json"
    assert (
        "Expected at least 1 instances of Root Data Entity (Dataset), found 0 valid."
        in (error["message"])
    )
    assert "./" in error["message"]
    assert "license" in error["message"] and "missing" in error["message"]
    detail = only_row(rows, "#Root", "./", "license")
    assert detail["severity"] == "info" and not detail["passed"]
    assert not ValidationReport(rows).is_valid
    assert run.cardinalities == [CardinalityOutcome("#Root", False, 0)]

    root = {"@id": "./", "@type": "Dataset", "license": "CC-BY"}
    run, rows = validate(ROOT_RULES, root=root)
    assert errors(rows) == []
    card = only_row(rows, "#Root", None, None)
    assert card["passed"] and card["severity"] is None
    assert card["message"] == (
        "Found 1 valid instances of Root Data Entity (Dataset) (expected between 1 and 1)"
    )
    assert only_row(rows, "#Root", "./", "license")["passed"]
    assert ValidationReport(rows).is_valid


def test_near_miss_lists_at_most_five():
    rules = (
        cls("#Person", {"@id": "Person"}, min_count=1),
        prop("#name", "name", "#Person", min_count=1),
    )
    people = [{"@id": f"#p{i}", "@type": "Person"} for i in range(7)]
    _, rows = validate(rules, *people)
    [error] = errors(rows)
    assert (
        "Near misses: #p0: property `name`: missing required property | #p1:" in (error["message"])
    )
    assert "#p4" in error["message"] and "#p5" not in error["message"]
    assert error["message"].endswith(" (+2 more)")


def test_above_maximum_is_error():
    rules = (cls("#Person", {"@id": "Person"}, name="Person", max_count=1),)
    _, rows = validate(rules, {"@id": "#a", "@type": "Person"}, {"@id": "#b", "@type": "Person"})
    [error] = errors(rows)
    assert error["message"] == "Expected at most 1 instances of Person (Person), found 2 valid."


def test_near_miss_with_class_min_zero_is_info_only():
    rules = (
        cls("#Person", {"@id": "Person"}, min_count=0),
        prop("#name", "name", "#Person", min_count=1),
    )
    _, rows = validate(rules, {"@id": "#p1", "@type": "Person"})
    assert errors(rows) == []
    failures = [r for r in rows if not r["passed"]]
    assert failures == [only_row(rows, "#Person", "#p1", "name")]
    assert failures[0]["severity"] == "info"
    assert "missing required property" in failures[0]["message"]


def test_too_many_values_is_error_with_entity_and_property():
    rules = (
        cls("#Person", {"@id": "Person"}),
        prop("#name", "name", "#Person", max_count=1),
    )
    run, rows = validate(rules, {"@id": "#p1", "@type": "Person", "name": ["A", "B"]})
    [error] = errors(rows)
    assert error["entity_id"] == "#p1" and error["property"] == "name"
    assert error["rule"] == "#Person"
    assert "allows at most 1" in error["message"]
    [outcome] = run.outcomes
    assert outcome == ("#Person", "#p1", "#name", False, "error")


def test_discriminator_property_value_does_not_error_other_creativeworks():
    rules = (
        cls("#Descriptor", {"@id": "CreativeWork"}, min_count=1, max_count=1),
        prop("#about-id", "@id", "#Descriptor", ["#descriptor-id"], min_count=1),
        pv("#descriptor-id", "ro-crate-metadata.json", min_count=1, max_count=1),
    )
    run, rows = validate(rules, {"@id": "#doc", "@type": "CreativeWork", "name": "Doc"})
    assert errors(rows) == []
    assert valid_counts(run) == {"#Descriptor": 1}
    doc_row = only_row(rows, "#Descriptor", "#doc", "@id")
    assert doc_row["severity"] == "info"
    assert only_row(rows, "#Descriptor", "ro-crate-metadata.json", "@id")["passed"]


PERSON_RULES = (
    cls("#Root", {"@id": "Dataset"}, min_count=1),
    prop("#author", "author", "#Root", ["#Person"]),
    cls("#Person", {"@id": "Person"}, name="Person"),
    prop("#name", "name", "#Person", ["Text"], min_count=1),
)


def test_reference_range_recurses_and_reports_chain():
    root = {"@id": "./", "@type": "Dataset", "author": {"@id": "#p1"}}
    _, rows = validate(PERSON_RULES, {"@id": "#p1", "@type": "Person"}, root=root)
    chain = "value `#p1` is not a valid Person: property `name`: missing required property"
    author = only_row(rows, "#Root", "./", "author")
    assert author["severity"] == "info"
    assert chain in author["message"]
    [error] = errors(rows)
    assert chain in error["message"]


def test_reference_to_valid_entity_passes():
    root = {"@id": "./", "@type": "Dataset", "author": {"@id": "#p1"}}
    run, rows = validate(PERSON_RULES, {"@id": "#p1", "@type": "Person", "name": "A"}, root=root)
    assert [r for r in rows if not r["passed"]] == []
    assert valid_counts(run) == {"#Root": 1, "#Person": 1}


def test_reference_with_wrong_types_gives_js_style_reason():
    root = {"@id": "./", "@type": "Dataset", "author": {"@id": "#o1"}}
    _, rows = validate(PERSON_RULES, {"@id": "#o1", "@type": "Organization"}, root=root)
    author = only_row(rows, "#Root", "./", "author")
    assert (
        'value "#o1" (types: Organization) did not match any of the expected ranges: #Person'
        in (author["message"])
    )


CYCLE_RULES = (
    cls("#A", {"@id": "Person"}),
    prop("#knows", "knows", "#A", ["#B"]),
    cls("#B", {"@id": "Organization"}),
    prop("#member", "member", "#B", ["#A"]),
)
CYCLE_ENTITIES = (
    {"@id": "#a", "@type": "Person", "knows": {"@id": "#b"}},
    {"@id": "#b", "@type": "Organization", "member": {"@id": "#a"}},
)


def assert_rows_unique(rows):
    keys = Counter((r["rule"], r["entity_id"], r["property"]) for r in rows)
    assert [k for k, n in keys.items() if n > 1] == []


def test_mutual_references_terminate():
    _, rows = validate(CYCLE_RULES, *CYCLE_ENTITIES)
    assert_rows_unique(rows)
    self_loop = (cls("#A", {"@id": "Person"}), prop("#knows", "knows", "#A", ["#A"]))
    _, rows = validate(self_loop, {"@id": "#a", "@type": "Person", "knows": {"@id": "#a"}})
    assert only_row(rows, "#A", "#a", "knows")["passed"]


def test_passing_cycle_both_valid():
    run, rows = validate(CYCLE_RULES, *CYCLE_ENTITIES)
    assert valid_counts(run) == {"#A": 1, "#B": 1}
    assert [r for r in rows if not r["passed"]] == []
    assert sorted(o.entity_id for o in run.outcomes) == ["#a", "#b"]


def test_failing_cycle_is_order_independent():
    a_rules = (
        cls("#A", {"@id": "Person"}),
        prop("#knows", "knows", "#A", ["#B"]),
        prop("#name", "name", "#A", min_count=1),
    )
    b_rules = (cls("#B", {"@id": "Organization"}), prop("#member", "member", "#B", ["#A"]))
    for rules in (a_rules + b_rules, b_rules + a_rules):
        run, rows = validate(rules, *CYCLE_ENTITIES)
        assert valid_counts(run) == {"#A": 0, "#B": 0}
        assert_rows_unique(rows)
        assert not only_row(rows, "#B", "#b", "member")["passed"]
        assert not only_row(rows, "#A", "#a", "name")["passed"]
        # A's link to B passed under the assumption that A was valid; once A
        # fails, the row is rechecked and shows B's failure.
        knows = only_row(rows, "#A", "#a", "knows")
        assert not knows["passed"]
        assert "value `#b` is not a valid #B: property `member`: value `#a`" in knows["message"]


def test_empty_list_counts_as_missing():
    rules = (cls("#Person", {"@id": "Person"}), prop("#name", "name", "#Person", min_count=1))
    _, rows = validate(rules, {"@id": "#p1", "@type": "Person", "name": []})
    row = only_row(rows, "#Person", "#p1", "name")
    assert not row["passed"] and "missing required property" in row["message"]
    optional = (cls("#Person", {"@id": "Person"}), prop("#name", "name", "#Person"))
    _, rows = validate(optional, {"@id": "#p1", "@type": "Person", "name": []})
    assert only_row(rows, "#Person", "#p1", "name")["passed"]


def test_too_few_values_is_info():
    rules = (cls("#Person", {"@id": "Person"}), prop("#name", "name", "#Person", min_count=2))
    _, rows = validate(rules, {"@id": "#p1", "@type": "Person", "name": "A"})
    row = only_row(rows, "#Person", "#p1", "name")
    assert row["severity"] == "info" and "requires at least 2" in row["message"]


def test_value_matching_property_value_is_exempt_from_other_ranges():
    rules = (
        cls("#Person", {"@id": "Person"}),
        prop("#kind", "kind", "#Person", ["#pv_fixed", "Text"]),
        pv("#pv_fixed", "#fixed"),
    )
    _, rows = validate(rules, {"@id": "#p1", "@type": "Person", "kind": {"@id": "#fixed"}})
    assert only_row(rows, "#Person", "#p1", "kind")["passed"]
    _, rows = validate(rules, {"@id": "#p1", "@type": "Person", "kind": {"@id": "#other"}})
    row = only_row(rows, "#Person", "#p1", "kind")
    assert "references an entity that does not exist in the crate" in row["message"]


def test_property_value_max_violation_is_info():
    rules = (
        cls("#Person", {"@id": "Person"}, min_count=0),
        prop("#kind", "kind", "#Person", ["#pv", "Text"]),
        pv("#pv", "/^x/", max_count=1),
    )
    _, rows = validate(rules, {"@id": "#p1", "@type": "Person", "kind": ["x1", "x2"]})
    row = only_row(rows, "#Person", "#p1", "kind")
    assert row["severity"] == "info"
    assert "allows at most 1 match(es), found 2" in row["message"]
    assert ValidationReport(rows).is_valid


def test_property_value_min_violation_is_info():
    rules = (
        cls("#Person", {"@id": "Person"}),
        prop("#kind", "kind", "#Person", ["#pv"]),
        pv("#pv", "fixed", min_count=1),
    )
    _, rows = validate(rules, {"@id": "#p1", "@type": "Person", "kind": "other"})
    row = only_row(rows, "#Person", "#p1", "kind")
    assert row["severity"] == "info" and "requires at least 1 match(es), found 0" in row["message"]


def test_property_value_only_ranges_allow_other_values():
    rules = (
        cls("#Person", {"@id": "Person"}),
        prop("#kind", "kind", "#Person", ["#pv"]),
        pv("#pv", "fixed", min_count=1),
    )
    _, rows = validate(rules, {"@id": "#p1", "@type": "Person", "kind": ["fixed", "other", 3]})
    assert only_row(rows, "#Person", "#p1", "kind")["passed"]


def test_failed_class_range_does_not_fall_back_to_template(monkeypatch):
    template_calls = []

    def always_matches(actual, template):
        template_calls.append(template.id)
        return True

    monkeypatch.setattr(engine, "matches_template", always_matches)
    root = {"@id": "./", "@type": "Dataset", "author": {"@id": "#p1"}}
    _, rows = validate(PERSON_RULES, {"@id": "#p1", "@type": "Person"}, root=root)
    assert not only_row(rows, "#Root", "./", "author")["passed"]
    assert template_calls == []


def test_empty_specialization_class_is_skipped():
    rules = (
        cls("#Empty", [], min_count=1),
        prop("#name", "name", "#Empty", min_count=1),
    )
    run, rows = validate(rules, {"@id": "#p1", "@type": "Person"})
    assert [r for r in rows if r["rule"] == "#Empty"] == []
    assert run.cardinalities == [] and run.outcomes == []


URL_RULES = (cls("#Root", {"@id": "Dataset"}), prop("#license", "license", "#Root", ["URL"]))


def test_dangling_relative_reference_fails():
    root = {"@id": "./", "@type": "Dataset", "license": {"@id": "#alice"}}
    _, rows = validate(URL_RULES, root=root)
    row = only_row(rows, "#Root", "./", "license")
    assert row["severity"] == "info"
    assert (
        'value "#alice" references an entity that does not exist in the crate' in (row["message"])
    )


def test_absolute_iri_reference_satisfies_url_range():
    licence = "https://creativecommons.org/licenses/by/4.0/"
    root = {"@id": "./", "@type": "Dataset", "license": {"@id": licence}}
    _, rows = validate(URL_RULES, root=root)
    assert only_row(rows, "#Root", "./", "license")["passed"]
    expanded = (
        cls("#Root", {"@id": "Dataset"}),
        prop("#license", "license", "#Root", ["http://schema.org/URL"]),
    )
    _, rows = validate(expanded, root=root)
    assert only_row(rows, "#Root", "./", "license")["passed"]
    text_only = (cls("#Root", {"@id": "Dataset"}), prop("#license", "license", "#Root", ["Text"]))
    _, rows = validate(text_only, root=root)
    assert not only_row(rows, "#Root", "./", "license")["passed"]


@pytest.mark.parametrize("bad_iri", ["http://[", "https://exa mple.org/x", "http://"])
def test_malformed_absolute_reference_does_not_satisfy_url_range(bad_iri):
    root = {"@id": "./", "@type": "Dataset", "license": {"@id": bad_iri}}
    _, rows = validate(URL_RULES, root=root)
    row = only_row(rows, "#Root", "./", "license")
    assert not row["passed"]
    assert "references an entity that does not exist in the crate" in row["message"]


def test_enumeration_and_itemlist_and_template_ranges():
    rules = (
        cls("#Root", {"@id": "Dataset"}),
        prop("#licence", "license", "#Root", ["#LicenceEnum"]),
        prop("#language", "inLanguage", "#Root", ["#langs"]),
        prop("#publisher", "publisher", "#Root", ["https://example.org/press"]),
        {"@id": "#langs", "@type": "ItemList", "itemListElement": [{"@id": "#en"}]},
    )
    extra = (
        {
            "@id": "#LicenceEnum",
            "@type": "rdfs:Class",
            "rdfs:subClassOf": {"@id": "http://schema.org/Enumeration"},
        },
        {"@id": "#cc-by", "@type": "#LicenceEnum"},
        {"@id": "#en", "@type": "Language", "name": "English"},
        {"@id": "https://example.org/press", "@type": "Organization", "name": "Press"},
    )
    good = (
        {"@id": "#cc-by", "@type": "CreativeWork"},
        {"@id": "#en", "@type": "Language", "name": "English"},
        {"@id": "https://example.org/press", "@type": "Organization", "name": "Press"},
    )
    root = {
        "@id": "./",
        "@type": "Dataset",
        "license": {"@id": "#cc-by"},
        "inLanguage": {"@id": "#en"},
        "publisher": {"@id": "https://example.org/press"},
    }
    _, rows = validate(rules, *good, root=root, extra=extra)
    for name in ("license", "inLanguage", "publisher"):
        assert only_row(rows, "#Root", "./", name)["passed"], name

    bad = (
        {"@id": "#cc-by", "@type": "CreativeWork"},
        {"@id": "#mit", "@type": "CreativeWork"},
        {"@id": "#en", "@type": "Language", "name": "Anglais"},
        {"@id": "https://example.org/press", "@type": "Organization", "name": "Other"},
    )
    root = {**root, "license": {"@id": "#mit"}}
    _, rows = validate(rules, *bad, root=root, extra=extra)
    for name in ("license", "inLanguage", "publisher"):
        assert not only_row(rows, "#Root", "./", name)["passed"], name


def test_matches_property_by_iri_not_spelling():
    rules = (
        cls("#Root", {"@id": "Dataset"}),
        prop("#holder", "dct:rightsHolder", "#Root", min_count=1),
    )
    context = [*DEFAULT_CONTEXT, {"rightsHolder": "http://purl.org/dc/terms/rightsHolder"}]
    root = {"@id": "./", "@type": "Dataset", "rightsHolder": "Someone"}
    _, rows = validate(rules, root=root, crate_context=context)
    assert only_row(rows, "#Root", "./", "dct:rightsHolder")["passed"]
    _, rows = validate(rules, root=root)
    assert not only_row(rows, "#Root", "./", "dct:rightsHolder")["passed"]


def test_literal_range_checks_expanded_and_raw_forms():
    # The profile's @vocab sends bare "Text" elsewhere, so only the raw form matches.
    context = [{"@vocab": "http://example.org/", "s": "http://schema.org/"}]
    rules = (
        cls("#Person", {"@id": "http://schema.org/Person"}),
        prop("#name", "http://schema.org/name", "#Person", ["Text"]),
        prop("#age", "http://schema.org/age", "#Person", ["s:Integer"]),
    )
    person = {"@id": "#p1", "@type": "Person", "name": "A", "age": 3}
    _, rows = validate(rules, person, profile_context=context)
    assert only_row(rows, "#Person", "#p1", "http://schema.org/name")["passed"]
    assert only_row(rows, "#Person", "#p1", "http://schema.org/age")["passed"]
    _, rows = validate(rules, {**person, "age": "three"}, profile_context=context)
    row = only_row(rows, "#Person", "#p1", "http://schema.org/age")
    assert row["message"].endswith(
        'value "three" did not match any of the expected ranges: s:Integer'
    )


def test_unnamed_property_rule_fails_entity_with_warning():
    rules = (
        cls("#Person", {"@id": "Person"}),
        {"@id": "#nameless", "@type": "rdf:Property", "domainIncludes": {"@id": "#Person"}},
    )
    run, rows = validate(rules, {"@id": "#p1", "@type": "Person"})
    row = only_row(rows, "#Person", "#p1", "#nameless")
    assert row["severity"] == "warning"
    assert valid_counts(run) == {"#Person": 0}


def test_unsupported_regex_flags_warn_once_per_rule():
    rules = (
        cls("#Person", {"@id": "Person"}),
        prop("#kind", "kind", "#Person", ["#pv"]),
        pv("#pv", "/a/x", "/b/zi", "plain"),
        pv("#ok", "/c/gi"),
    )
    _, rows = validate(rules, {"@id": "#p1", "@type": "Person", "kind": "a"})
    warnings = [r for r in rows if r["rule"] == "profile"]
    assert warnings == [rows[0]]
    [warning] = warnings
    assert warning["entity_id"] == "#pv" and warning["property"] is None
    assert warning["severity"] == "warning" and not warning["passed"]
    assert "x" in warning["message"] and "z" in warning["message"]
    assert warning["source"] == "profile.json"


def test_each_entity_class_pair_evaluated_once(monkeypatch):
    calls = []
    original = ValidationRun.check_property

    def counting(self, node, prule):
        calls.append((node.id, prule.id))
        return original(self, node, prule)

    monkeypatch.setattr(ValidationRun, "check_property", counting)
    rules = (
        cls("#Work", {"@id": "CreativeWork"}),
        prop("#author", "author", "#Work", ["#Person"]),
        cls("#Person", {"@id": "Person"}),
        prop("#name", "name", "#Person", min_count=1),
    )
    works = [
        {"@id": f"#w{i}", "@type": "CreativeWork", "author": {"@id": "#p1"}} for i in range(5)
    ]
    run, rows = validate(rules, *works, {"@id": "#p1", "@type": "Person", "name": "A"})
    assert Counter(calls).most_common(1)[0][1] == 1
    assert ("#p1", "#name") in calls
    # Five works plus the metadata descriptor, then the person.
    assert len(calls) == 7
    assert len(run.outcomes) == 7
    assert_rows_unique(rows)


def test_odd_shapes_do_not_crash():
    rules = (
        cls("#Person", {"@id": "Person"}),
        prop("#name", "name", "#Person", ["Text"], min_count=1),
        prop("#knows", "knows", "#Person", ["#Person", "URL"]),
    )
    entities = (
        {"@id": "#untyped", "name": "x"},
        {"@id": "#p1", "@type": "Person", "name": {"@value": "Alice"}},
        {
            "@id": "#p2",
            "@type": ["Person", 7],
            "name": {"inline": "no id"},
            "knows": [{"@id": 5}, {"@id": ""}, {"@id": {"x": 1}}, [1, 2], None],
        },
    )
    run, rows = validate(rules, *entities)
    assert entity_rows(rows, "#untyped") == []
    assert only_row(rows, "#Person", "#p1", "name")["passed"]
    name = only_row(rows, "#Person", "#p2", "name")
    assert not name["passed"] and '{"inline":"no id"}' in name["message"]
    assert not only_row(rows, "#Person", "#p2", "knows")["passed"]
    assert valid_counts(run) == {"#Person": 1}


def count_evaluations(monkeypatch):
    calls = []
    original = ValidationRun._evaluate

    def counting(self, node, class_rule):
        calls.append((node.id, class_rule.id))
        return original(self, node, class_rule)

    monkeypatch.setattr(ValidationRun, "_evaluate", counting)
    return calls


KNOWS_RULES = (cls("#P", {"@id": "Person"}), prop("#knows", "knows", "#P", ["#P"]))


def test_dense_cycle_checks_each_pair_once(monkeypatch):
    calls = count_evaluations(monkeypatch)
    ids = [f"#p{i}" for i in range(12)]
    people = [
        {"@id": i, "@type": "Person", "knows": [{"@id": j} for j in ids if j != i]} for i in ids
    ]
    run, rows = validate(KNOWS_RULES, *people)
    assert valid_counts(run) == {"#P": 12}
    assert len(calls) == 12
    assert_rows_unique(rows)


def test_dense_cycle_with_one_failure_is_invalid_throughout(monkeypatch):
    calls = count_evaluations(monkeypatch)
    rules = (*KNOWS_RULES, prop("#name", "name", "#P", min_count=1))
    ids = [f"#p{i}" for i in range(12)]
    people = [
        {"@id": i, "@type": "Person", "name": i, "knows": [{"@id": j} for j in ids if j != i]}
        for i in ids
    ]
    del people[7]["name"]
    run, rows = validate(rules, *people)
    # Everyone knows #p7, who has no name, so nobody is valid.
    assert valid_counts(run) == {"#P": 0}
    assert len(calls) < 12 * 12
    assert_rows_unique(rows)


def chain(length, *, ring=False, name_last=True):
    people = []
    for i in range(length):
        knows = [{"@id": f"#p{i + 1}"}] if i + 1 < length else []
        if ring:
            knows.append({"@id": f"#p{(i - 1) % length}"})
            knows.append({"@id": f"#p{(i + 1) % length}"})
        person = {"@id": f"#p{i}", "@type": "Person", "knows": knows}
        if i + 1 < length or name_last:
            person["name"] = f"P{i}"
        people.append(person)
    return people


def test_long_reference_chains_do_not_exhaust_the_stack():
    rules = (*KNOWS_RULES, prop("#name", "name", "#P", min_count=1))
    for length in (1000, 5000):
        run, rows = validate(rules, *chain(length))
        assert valid_counts(run) == {"#P": length}
    # The last entity lacks a name, so every entity before it fails too.
    run, rows = validate(rules, *chain(5000, name_last=False))
    assert valid_counts(run) == {"#P": 0}
    first = only_row(rows, "#P", "#p0", "knows")
    assert first["message"].startswith("Property `knows`: value `#p1` is not a valid #P")
    assert len(first["message"]) < 1000  # nested reasons are cut short
    run, _ = validate(rules, *chain(5000, ring=True))
    assert valid_counts(run) == {"#P": 5000}


def test_recursion_error_becomes_value_error(monkeypatch):
    def too_deep(self, node, prule):
        raise RecursionError

    monkeypatch.setattr(ValidationRun, "check_property", too_deep)
    with pytest.raises(ValueError, match="nest too deeply"):
        validate(KNOWS_RULES, {"@id": "#p1", "@type": "Person"})


def test_null_and_empty_string_count_as_missing():
    rules = (cls("#Person", {"@id": "Person"}), prop("#name", "name", "#Person", min_count=1))
    for empty in ("", None, [None, ""]):
        _, rows = validate(rules, {"@id": "#p1", "@type": "Person", "name": empty})
        row = only_row(rows, "#Person", "#p1", "name")
        assert row["severity"] == "info", empty
        assert row["message"].endswith("missing required property"), empty


def test_zero_and_false_count_as_present():
    rules = (
        cls("#Person", {"@id": "Person"}),
        prop("#flag", "flag", "#Person", ["Boolean"], min_count=1),
        prop("#count", "count", "#Person", ["Integer"], min_count=1),
    )
    _, rows = validate(rules, {"@id": "#p1", "@type": "Person", "flag": False, "count": 0})
    assert only_row(rows, "#Person", "#p1", "flag")["passed"]
    assert only_row(rows, "#Person", "#p1", "count")["passed"]
