"""Tests for JSON-LD context resolution and term expansion."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("rdflib")

from rdflib.plugins.shared.jsonld.context import Context

from crategraph.validators.masp import context as context_module
from crategraph.validators.masp.context import (
    BUNDLED_CONTEXTS,
    TermExpander,
    normalise_iri,
    resolve_context,
)

REPO = Path(__file__).resolve().parents[3]
LDAC_CONTEXTS = (
    "http://purl.archive.org/language-data-commons/context.json",
    "https://w3id.org/ldac/context",
)


def _boom(*args, **kwargs):
    raise AssertionError("network access attempted")


class _Response(io.BytesIO):
    """A minimal stand-in for the object ``urlopen`` returns."""


def _fake_response(document, calls=None):
    def urlopen(request, timeout=None):
        if calls is not None:
            calls.append((request, timeout))
        return _Response(json.dumps(document).encode())

    return urlopen


@pytest.fixture(autouse=True)
def _clear_fetch_cache():
    context_module._FETCH_CACHE.clear()
    yield
    context_module._FETCH_CACHE.clear()


def _strings_anywhere(value):
    """Yield every string value (not dict keys) nested in *value*."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings_anywhere(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings_anywhere(item)


# --- resolve_context ---------------------------------------------------------


def test_bundled_ro_crate_context_inlines_without_network(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    res = resolve_context(
        ["https://w3id.org/ro/crate/1.2/context", {"@vocab": "http://schema.org/"}]
    )
    assert res.unresolved == ()
    assert all(not isinstance(c, str) for c in res.context)


@pytest.mark.parametrize("url", sorted(BUNDLED_CONTEXTS))
def test_every_bundled_context_loads(monkeypatch, url):
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    res = resolve_context(url)
    assert res.unresolved == ()
    assert len(res.context) == 1
    assert isinstance(res.context[0], dict) and res.context[0]


@pytest.mark.parametrize(
    "variant",
    [
        "http://w3id.org/ro/crate/1.1/context",
        "https://w3id.org/ro/crate/1.1/context/",
        "http://w3id.org/ro/crate/1.1/context/",
    ],
)
def test_bundled_lookup_ignores_trailing_slash_and_scheme(monkeypatch, variant):
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    res = resolve_context(variant, fetch=True)
    assert res.unresolved == ()
    assert TermExpander(res.context).expand("Dataset") == "http://schema.org/Dataset"


def test_bundled_context_is_a_fresh_copy_each_time():
    first = resolve_context("https://w3id.org/ro/crate/1.2/context").context[0]
    first["Dataset"] = "http://example.org/Mutated"
    second = resolve_context("https://w3id.org/ro/crate/1.2/context").context[0]
    assert second["Dataset"] == "http://schema.org/Dataset"


def test_single_dict_and_none_contexts():
    assert resolve_context({"ex": "http://ex.org/"}).context == [{"ex": "http://ex.org/"}]
    assert resolve_context(None) == ([], ())


def test_unknown_url_unresolved_without_fetch(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    res = resolve_context(["https://example.org/ctx.jsonld"])
    assert res.unresolved == ("https://example.org/ctx.jsonld",)
    assert res.context == []


def test_fetch_true_uses_fetched_document(monkeypatch):
    calls = []
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        _fake_response({"@context": {"ex": "http://ex.org/"}}, calls),
    )
    res = resolve_context(["https://example.org/ctx.jsonld"], fetch=True)
    assert res.unresolved == ()
    assert TermExpander(res.context).expand("ex:thing") == "http://ex.org/thing"

    request, timeout = calls[0]
    assert request.full_url == "https://example.org/ctx.jsonld"
    assert request.get_header("Accept") == "application/ld+json, application/json"
    assert timeout == 30


def test_fetched_document_is_cached_per_process(monkeypatch):
    calls = []
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        _fake_response({"@context": {"ex": "http://ex.org/"}}, calls),
    )
    resolve_context("https://example.org/ctx.jsonld", fetch=True)
    resolve_context("https://example.org/ctx.jsonld", fetch=True)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("unreachable"),
        urllib.error.HTTPError("https://example.org/ctx.jsonld", 404, "Not Found", {}, None),
        TimeoutError("timed out"),
    ],
)
def test_fetch_failure_is_unresolved_not_raised(monkeypatch, error):
    def failing(*args, **kwargs):
        raise error

    monkeypatch.setattr(urllib.request, "urlopen", failing)
    res = resolve_context(["https://example.org/ctx.jsonld", {"ex": "http://ex.org/"}], fetch=True)
    assert res.unresolved == ("https://example.org/ctx.jsonld",)
    assert res.context == [{"ex": "http://ex.org/"}]


@pytest.mark.parametrize("document", ["not json at all", {"no": "context"}, ["a", "list"]])
def test_fetched_document_without_context_is_unresolved(monkeypatch, document):
    if isinstance(document, str):
        monkeypatch.setattr(
            urllib.request, "urlopen", lambda *a, **k: _Response(document.encode())
        )
    else:
        monkeypatch.setattr(urllib.request, "urlopen", _fake_response(document))
    res = resolve_context("https://example.org/ctx.jsonld", fetch=True)
    assert res.unresolved == ("https://example.org/ctx.jsonld",)


def test_nested_remote_contexts_resolve_recursively_against_their_document(monkeypatch):
    documents = {
        "https://example.org/a/outer.jsonld": {
            "@context": ["inner.jsonld", {"outer": "http://ex.org/outer"}]
        },
        "https://example.org/a/inner.jsonld": {"@context": {"inner": "http://ex.org/inner"}},
    }

    def urlopen(request, timeout=None):
        return _Response(json.dumps(documents[request.full_url]).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    res = resolve_context("https://example.org/a/outer.jsonld", fetch=True)
    assert res.unresolved == ()
    assert not any(isinstance(c, str) for c in res.context)
    exp = TermExpander(res.context)
    assert exp.expand("inner") == "http://ex.org/inner"
    assert exp.expand("outer") == "http://ex.org/outer"


def test_context_cycle_terminates(monkeypatch):
    documents = {
        "https://example.org/a.jsonld": {
            "@context": ["https://example.org/b.jsonld", {"a": "http://ex.org/a"}]
        },
        "https://example.org/b.jsonld": {
            "@context": ["https://example.org/a.jsonld", {"b": "http://ex.org/b"}]
        },
    }

    def urlopen(request, timeout=None):
        return _Response(json.dumps(documents[request.full_url]).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    res = resolve_context("https://example.org/a.jsonld", fetch=True)
    assert not any(isinstance(c, str) for c in res.context)
    exp = TermExpander(res.context)
    assert exp.expand("a") == "http://ex.org/a"
    assert exp.expand("b") == "http://ex.org/b"


def test_at_import_is_resolved_and_rdflib_never_fetches(monkeypatch):
    monkeypatch.setattr(Context, "_fetch_context", _boom)
    res = resolve_context(
        [{"@import": "https://w3id.org/ro/crate/1.2/context", "ex": "http://ex.org/"}]
    )
    assert "@import" not in json.dumps(res.context)
    assert res.unresolved == ()
    exp = TermExpander(res.context)
    assert exp.expand("Dataset") == "http://schema.org/Dataset"
    assert exp.expand("ex:thing") == "http://ex.org/thing"


def test_at_import_terms_lose_to_the_importing_dict():
    res = resolve_context(
        [{"@import": "https://w3id.org/ro/crate/1.2/context", "name": "http://ex.org/name"}]
    )
    assert TermExpander(res.context).expand("name") == "http://ex.org/name"


def test_unresolved_at_import_is_dropped_and_reported(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    res = resolve_context([{"@import": "https://example.org/imp.jsonld", "ex": "http://ex.org/"}])
    assert res.unresolved == ("https://example.org/imp.jsonld",)
    assert res.context == [{"ex": "http://ex.org/"}]


def test_scoped_context_urls_are_inlined(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    res = resolve_context(
        [
            {
                "thing": {
                    "@id": "http://ex.org/thing",
                    "@context": "https://w3id.org/ro/crate/1.2/context",
                }
            }
        ]
    )
    assert res.unresolved == ()
    scoped = res.context[0]["thing"]["@context"]
    assert isinstance(scoped, list) and isinstance(scoped[0], dict)
    assert "https://w3id.org/ro/crate/1.2/context" not in set(_strings_anywhere(res.context))


def test_unresolved_urls_are_reported_once_in_order(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    res = resolve_context(
        [
            "https://example.org/b.jsonld",
            "https://example.org/a.jsonld",
            "https://example.org/b.jsonld",
        ]
    )
    assert res.unresolved == ("https://example.org/b.jsonld", "https://example.org/a.jsonld")


def test_tutorial_nt1_context_fully_bundled(monkeypatch):
    missing = [url for url in LDAC_CONTEXTS if url not in BUNDLED_CONTEXTS]
    if missing:
        pytest.skip(
            "LDaC contexts are not bundled (their hosting repositories are GPL-3.0; "
            f"see crategraph/validators/masp/contexts/README.md): {missing}"
        )
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    data = json.loads(
        (REPO / "docs/tutorials/data/paradisec/NT1/ro-crate-metadata.json").read_text()
    )
    assert resolve_context(data["@context"]).unresolved == ()


def test_tutorial_nt1_reports_only_the_unbundled_ldac_contexts(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    data = json.loads(
        (REPO / "docs/tutorials/data/paradisec/NT1/ro-crate-metadata.json").read_text()
    )
    res = resolve_context(data["@context"])
    expected = tuple(url for url in LDAC_CONTEXTS if url not in BUNDLED_CONTEXTS)
    assert res.unresolved == expected
    exp = TermExpander(res.context)
    assert exp.expand("Dataset") == "http://schema.org/Dataset"
    assert exp.expand("asWKT") == "http://www.opengis.net/ont/geosparql#asWKT"


# --- TermExpander ------------------------------------------------------------


def test_expander_vocab_prefix_and_term():
    exp = TermExpander(
        [
            {
                "@vocab": "http://schema.org/",
                "dct": "http://purl.org/dc/terms/",
                "rightsHolder": "dct:rightsHolder",
            }
        ]
    )
    assert exp.expand("name") == "http://schema.org/name"
    assert exp.expand("dct:rightsHolder") == "http://purl.org/dc/terms/rightsHolder"
    assert exp.expand("rightsHolder") == "http://purl.org/dc/terms/rightsHolder"
    assert exp.expand("@id") == "@id"
    assert exp.expand("#Root") == "#Root"


def test_expander_guards_keywords_and_relative_ids_even_with_vocab():
    exp = TermExpander([{"@vocab": "http://schema.org/"}])
    for t in [
        "@id",
        "@type",
        "#Root",
        "./",
        "../x",
        "https://example.org/a",
        "http://schema.org/name",
        "urn:x:1",
        "undefinedprefix:thing",
    ]:
        assert exp.expand(t) == t


def test_expander_expands_ro_crate_terms():
    res = resolve_context(["https://w3id.org/ro/crate/1.2/context"])
    exp = TermExpander(res.context)
    assert exp.expand("Dataset") == "http://schema.org/Dataset"
    assert exp.expand("conformsTo") == "http://purl.org/dc/terms/conformsTo"
    assert exp.expand("rdfs:label") == "http://www.w3.org/2000/01/rdf-schema#label"


def test_expander_without_vocab_returns_none_for_undefined_term():
    assert TermExpander([{"dct": "http://purl.org/dc/terms/"}]).expand("mystery") is None


def test_expander_caches_results(monkeypatch):
    exp = TermExpander([{"@vocab": "http://schema.org/"}])
    assert exp.expand("name") == "http://schema.org/name"
    monkeypatch.setattr(exp._context, "expand", _boom)
    assert exp.expand("name") == "http://schema.org/name"


def test_expander_rejects_unresolved_context_urls(monkeypatch):
    monkeypatch.setattr(Context, "_fetch_context", _boom)
    with pytest.raises(ValueError, match="resolve_context"):
        TermExpander(["https://example.org/ctx.jsonld"])


# --- normalise_iri -----------------------------------------------------------


def test_normalise_iri():
    assert normalise_iri("https://schema.org/Dataset") == "http://schema.org/Dataset"
    assert normalise_iri("http://schema.org/Dataset") == "http://schema.org/Dataset"
    assert normalise_iri("https://example.org/x") == "https://example.org/x"
