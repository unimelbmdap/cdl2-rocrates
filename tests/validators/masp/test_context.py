"""Tests for JSON-LD context resolution and term expansion."""

from __future__ import annotations

import email.message
import io
import json
import socket
import urllib.error
import urllib.request
import urllib.response
from pathlib import Path

import pytest

pytest.importorskip("rdflib")

from rdflib.plugins.shared.jsonld import context as rdflib_context
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


PUBLIC_ADDRESS = "93.184.215.14"


def _resolve_to(monkeypatch, addresses: dict[str, list[str]] | list[str], lookups=None):
    """Make host lookups return *addresses* (per host, or the same for every host)."""

    def getaddrinfo(host, port, *args, **kwargs):
        if lookups is not None:
            lookups.append(host)
        found = addresses.get(host, [PUBLIC_ADDRESS]) if isinstance(addresses, dict) else addresses
        return [
            (
                socket.AF_INET6 if ":" in a else socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                (a, port or 0),
            )
            for a in found
        ]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    """Every host resolves to a public address unless a test says otherwise."""
    _resolve_to(monkeypatch, [PUBLIC_ADDRESS])


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
    monkeypatch.setattr(context_module, "_open", _boom)
    res = resolve_context(
        ["https://w3id.org/ro/crate/1.2/context", {"@vocab": "http://schema.org/"}]
    )
    assert res.unresolved == ()
    assert all(not isinstance(c, str) for c in res.context)


@pytest.mark.parametrize("url", sorted(BUNDLED_CONTEXTS))
def test_every_bundled_context_loads(monkeypatch, url):
    monkeypatch.setattr(context_module, "_open", _boom)
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
    monkeypatch.setattr(context_module, "_open", _boom)
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
    monkeypatch.setattr(context_module, "_open", _boom)
    res = resolve_context(["https://example.org/ctx.jsonld"])
    assert res.unresolved == ("https://example.org/ctx.jsonld",)
    assert res.context == []


def test_allowed_url_uses_fetched_document(monkeypatch):
    calls = []
    monkeypatch.setattr(
        context_module,
        "_open",
        _fake_response({"@context": {"ex": "http://ex.org/"}}, calls),
    )
    res = resolve_context(
        ["https://example.org/ctx.jsonld"], fetch=["https://example.org/ctx.jsonld"]
    )
    assert res.unresolved == ()
    assert TermExpander(res.context).expand("ex:thing") == "http://ex.org/thing"

    request, timeout = calls[0]
    assert request.full_url == "https://example.org/ctx.jsonld"
    assert request.get_header("Accept") == "application/ld+json, application/json"
    assert timeout == 30


def test_fetched_document_is_cached_per_process(monkeypatch):
    calls = []
    monkeypatch.setattr(
        context_module,
        "_open",
        _fake_response({"@context": {"ex": "http://ex.org/"}}, calls),
    )
    resolve_context("https://example.org/ctx.jsonld", fetch=["https://example.org/ctx.jsonld"])
    resolve_context("https://example.org/ctx.jsonld", fetch=["https://example.org/ctx.jsonld"])
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

    monkeypatch.setattr(context_module, "_open", failing)
    res = resolve_context(
        ["https://example.org/ctx.jsonld", {"ex": "http://ex.org/"}],
        fetch=["https://example.org/ctx.jsonld"],
    )
    assert res.unresolved == ("https://example.org/ctx.jsonld",)
    assert res.context == [{"ex": "http://ex.org/"}]


@pytest.mark.parametrize("document", ["not json at all", {"no": "context"}, ["a", "list"]])
def test_fetched_document_without_context_is_unresolved(monkeypatch, document):
    if isinstance(document, str):
        monkeypatch.setattr(context_module, "_open", lambda *a, **k: _Response(document.encode()))
    else:
        monkeypatch.setattr(context_module, "_open", _fake_response(document))
    res = resolve_context(
        "https://example.org/ctx.jsonld", fetch=["https://example.org/ctx.jsonld"]
    )
    assert res.unresolved == ("https://example.org/ctx.jsonld",)


def test_relative_url_with_fetch_is_unresolved_not_raised(monkeypatch):
    monkeypatch.setattr(context_module, "_open", _boom)
    assert resolve_context(["ctx.jsonld"], fetch=["ctx.jsonld"]).unresolved == ("ctx.jsonld",)


@pytest.mark.parametrize("url", ["file:///etc/hosts", "ftp://example.org/x"])
def test_non_http_schemes_are_never_fetched(monkeypatch, url):
    monkeypatch.setattr(context_module, "_open", _boom)
    assert resolve_context([url], fetch=[url]).unresolved == (url,)


def test_malformed_url_with_fetch_is_unresolved_not_raised(monkeypatch):
    monkeypatch.setattr(context_module, "_open", _boom)
    assert resolve_context(["http://[abc"], fetch=["http://[abc"]).unresolved == ("http://[abc",)


def test_malformed_nested_url_is_unresolved_not_raised(monkeypatch):
    document = {"@context": ["//[abc/x", {"ex": "http://ex.org/"}]}
    monkeypatch.setattr(context_module, "_open", _fake_response(document))
    res = resolve_context(
        "https://example.org/ctx.jsonld", fetch=["https://example.org/ctx.jsonld"]
    )
    assert res.unresolved == ("//[abc/x",)
    assert res.context == [{"ex": "http://ex.org/"}]


PRIVATE_LITERAL_URLS = [
    "http://127.0.0.1:8080/admin",
    "http://10.0.0.5/ctx.jsonld",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/ctx.jsonld",
    "http://[fe80::1]/ctx.jsonld",
    "http://0.0.0.0/ctx.jsonld",
    "http://[::ffff:127.0.0.1]/ctx.jsonld",
]


@pytest.mark.parametrize("url", PRIVATE_LITERAL_URLS)
def test_private_literal_addresses_are_never_fetched(monkeypatch, url):
    monkeypatch.setattr(context_module, "_open", _boom)
    monkeypatch.setattr(socket, "getaddrinfo", _boom)  # a literal address needs no lookup
    assert resolve_context([url], fetch=[url]).unresolved == (url,)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "224.0.0.1",
        "0.0.0.0",
        "::1",
        "fe80::1%en0",
        "::ffff:10.0.0.1",
    ],
)
def test_hosts_resolving_to_private_addresses_are_never_fetched(monkeypatch, address):
    _resolve_to(monkeypatch, [address])
    monkeypatch.setattr(context_module, "_open", _boom)
    url = "https://internal.example.org/ctx.jsonld"
    assert resolve_context([url], fetch=[url]).unresolved == (url,)


def test_one_private_address_among_several_refuses_the_host(monkeypatch):
    _resolve_to(monkeypatch, [PUBLIC_ADDRESS, "10.0.0.1"])
    monkeypatch.setattr(context_module, "_open", _boom)
    url = "https://mixed.example.org/ctx.jsonld"
    assert resolve_context([url], fetch=[url]).unresolved == (url,)


def test_unresolvable_host_is_unresolved_not_raised(monkeypatch):
    def getaddrinfo(*args, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(context_module, "_open", _boom)
    url = "https://nowhere.example.org/ctx.jsonld"
    assert resolve_context([url], fetch=[url]).unresolved == (url,)


def test_public_address_is_checked_then_fetched(monkeypatch):
    lookups: list[str] = []
    _resolve_to(monkeypatch, [PUBLIC_ADDRESS], lookups)
    monkeypatch.setattr(
        context_module, "_open", _fake_response({"@context": {"ex": "http://ex.org/"}})
    )
    res = resolve_context(
        "https://example.org/ctx.jsonld", fetch=["https://example.org/ctx.jsonld"]
    )
    assert res.unresolved == ()
    assert lookups == ["example.org"]


class _FakeWeb(urllib.request.BaseHandler):
    """Serve canned responses for http(s) URLs: ``url -> (status, location or document)``."""

    handler_order = 50  # ahead of urllib's real handlers and any proxy handler

    def __init__(self, routes: dict[str, tuple[int, object]]) -> None:
        self.routes = routes
        self.requested: list[str] = []

    def _serve(self, request):
        url = request.full_url
        self.requested.append(url)
        status, payload = self.routes[url]
        headers = email.message.Message()
        if status in (301, 302, 303, 307, 308):
            headers["Location"] = payload
            body = b""
        else:
            body = json.dumps(payload).encode()
        response = urllib.response.addinfourl(io.BytesIO(body), headers, url, status)
        response.msg = "canned"
        return response

    http_open = _serve
    https_open = _serve


def _serve_web(monkeypatch, routes) -> _FakeWeb:
    """Route the real opener ``_open`` builds through a :class:`_FakeWeb`."""
    web = _FakeWeb(routes)
    real_build_opener = urllib.request.build_opener
    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *handlers: real_build_opener(*handlers, web)
    )
    return web


DOCUMENT = {"@context": {"ex": "http://ex.org/"}}


def test_redirect_to_public_host_is_followed(monkeypatch):
    start = "https://example.org/ctx.jsonld"
    final = "https://cdn.example.net/ctx.jsonld"
    web = _serve_web(monkeypatch, {start: (302, final), final: (200, DOCUMENT)})
    res = resolve_context(start, fetch=[start])
    assert res.unresolved == ()
    assert web.requested == [start, final]


@pytest.mark.parametrize(
    "target",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:8080/admin",
        "http://[::1]/ctx.jsonld",
        "https://internal.example.org/ctx.jsonld",
        "ftp://example.org/ctx.jsonld",
        "file:///etc/hosts",
    ],
)
def test_redirect_to_refused_address_is_unresolved(monkeypatch, target):
    _resolve_to(monkeypatch, {"internal.example.org": ["10.0.0.1"]})
    start = "https://example.org/ctx.jsonld"
    web = _serve_web(monkeypatch, {start: (302, target), target: (200, DOCUMENT)})
    res = resolve_context(start, fetch=[start])
    assert res.unresolved == (start,)
    assert web.requested == [start]


def test_too_many_redirects_is_unresolved(monkeypatch):
    hops = [f"https://example.org/hop{i}.jsonld" for i in range(8)]
    routes = {url: (302, hops[i + 1]) for i, url in enumerate(hops[:-1])}
    routes[hops[-1]] = (200, DOCUMENT)
    web = _serve_web(monkeypatch, routes)
    res = resolve_context(hops[0], fetch=[hops[0]])
    assert res.unresolved == (hops[0],)
    assert len(web.requested) <= 6


def test_nested_remote_contexts_resolve_recursively_against_their_document(monkeypatch):
    documents = {
        "https://example.org/a/outer.jsonld": {
            "@context": ["inner.jsonld", {"outer": "http://ex.org/outer"}]
        },
        "https://example.org/a/inner.jsonld": {"@context": {"inner": "http://ex.org/inner"}},
    }

    def urlopen(request, timeout=None):
        return _Response(json.dumps(documents[request.full_url]).encode())

    monkeypatch.setattr(context_module, "_open", urlopen)
    res = resolve_context("https://example.org/a/outer.jsonld", fetch=list(documents))
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

    monkeypatch.setattr(context_module, "_open", urlopen)
    res = resolve_context("https://example.org/a.jsonld", fetch=list(documents))
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
    monkeypatch.setattr(context_module, "_open", _boom)
    res = resolve_context([{"@import": "https://example.org/imp.jsonld", "ex": "http://ex.org/"}])
    assert res.unresolved == ("https://example.org/imp.jsonld",)
    assert res.context == [{"ex": "http://ex.org/"}]


def test_scoped_context_urls_are_inlined(monkeypatch):
    monkeypatch.setattr(context_module, "_open", _boom)
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


WRAPPED_URL = "https://example.org/ctx.jsonld"


@pytest.mark.parametrize(
    "context",
    [
        [{"@context": WRAPPED_URL}],
        [{"@context": [WRAPPED_URL]}],
        [{"@context": {"@import": WRAPPED_URL}}],
        {"@context": {"@context": WRAPPED_URL}},
    ],
    ids=["string", "list", "import", "doubly-wrapped"],
)
def test_wrapped_context_urls_are_resolved_not_left_for_rdflib(monkeypatch, context):
    monkeypatch.setattr(context_module, "_open", _boom)
    monkeypatch.setattr(rdflib_context, "source_to_json", _boom)
    res = resolve_context(context)
    assert res.unresolved == (WRAPPED_URL,)
    assert WRAPPED_URL not in set(_strings_anywhere(res.context))
    assert TermExpander(res.context).expand("ex:thing") == "ex:thing"


def test_wrapped_bundled_context_still_expands():
    res = resolve_context([{"@context": "https://w3id.org/ro/crate/1.2/context"}])
    assert res.unresolved == ()
    assert TermExpander(res.context).expand("Dataset") == "http://schema.org/Dataset"


@pytest.mark.parametrize(
    "context",
    [
        [{"@context": "file:///etc/hosts"}],
        [{"@import": "http://169.254.169.254/latest/meta-data/"}],
        [{"ex": "http://ex.org/", "@import": "http://127.0.0.1:6379/x"}],
    ],
)
def test_term_expander_refuses_to_load_any_context(monkeypatch, context):
    monkeypatch.setattr(rdflib_context, "source_to_json", _boom)
    with pytest.raises(ValueError, match="refusing to load context"):
        TermExpander(context)


def test_deeply_nested_contexts_raise_value_error():
    context: dict = {"@vocab": "http://schema.org/"}
    for i in range(400):
        context = {f"t{i}": {"@id": f"http://ex.org/t{i}", "@context": context}}
    with pytest.raises(ValueError, match="nested more than"):
        resolve_context([context])


def test_too_many_context_references_raise_value_error():
    with pytest.raises(ValueError, match="more than 100 times"):
        resolve_context(["https://w3id.org/ro/crate/1.2/context"] * 101)


def test_unresolved_urls_are_reported_once_in_order(monkeypatch):
    monkeypatch.setattr(context_module, "_open", _boom)
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
    monkeypatch.setattr(context_module, "_open", _boom)
    data = json.loads(
        (REPO / "docs/tutorials/data/paradisec/NT1/ro-crate-metadata.json").read_text()
    )
    assert resolve_context(data["@context"]).unresolved == ()


def test_tutorial_nt1_reports_only_the_unbundled_ldac_contexts(monkeypatch):
    monkeypatch.setattr(context_module, "_open", _boom)
    data = json.loads(
        (REPO / "docs/tutorials/data/paradisec/NT1/ro-crate-metadata.json").read_text()
    )
    res = resolve_context(data["@context"])
    expected = tuple(url for url in LDAC_CONTEXTS if url not in BUNDLED_CONTEXTS)
    assert res.unresolved == expected
    exp = TermExpander(res.context)
    assert exp.expand("Dataset") == "http://schema.org/Dataset"
    assert exp.expand("asWKT") == "http://www.opengis.net/ont/geosparql#asWKT"


# --- which contexts may be fetched ------------------------------------------


@pytest.mark.parametrize("url", LDAC_CONTEXTS)
def test_fetch_true_fetches_the_known_ldac_contexts(monkeypatch, url):
    calls = []
    monkeypatch.setattr(context_module, "_open", _fake_response(DOCUMENT, calls))
    res = resolve_context(url, fetch=True)
    assert res.unresolved == ()
    assert [request.full_url for request, _ in calls] == [url]


@pytest.mark.parametrize(
    "url",
    ["https://example.org/ctx.jsonld", "http://169.254.169.254/latest/meta-data/"],
)
def test_fetch_true_never_fetches_urls_the_crate_chooses(monkeypatch, url):
    monkeypatch.setattr(context_module, "_open", _boom)
    monkeypatch.setattr(socket, "getaddrinfo", _boom)
    assert resolve_context([url], fetch=True).unresolved == (url,)


def test_fetch_list_adds_urls_to_the_known_ones(monkeypatch):
    calls = []
    monkeypatch.setattr(context_module, "_open", _fake_response(DOCUMENT, calls))
    allowed = "https://example.org/ctx.jsonld"
    res = resolve_context(
        [allowed, LDAC_CONTEXTS[1], "https://other.example.org/ctx.jsonld"], fetch=[allowed]
    )
    assert res.unresolved == ("https://other.example.org/ctx.jsonld",)
    assert [request.full_url for request, _ in calls] == [allowed, LDAC_CONTEXTS[1]]


def test_fetch_accepts_a_single_url(monkeypatch):
    monkeypatch.setattr(context_module, "_open", _fake_response(DOCUMENT))
    url = "https://example.org/ctx.jsonld"
    assert resolve_context(url, fetch=url).unresolved == ()


def test_fetch_rejects_non_string_urls():
    with pytest.raises(TypeError, match="list of context URLs"):
        resolve_context([], fetch=[5])


def test_oversized_context_is_unresolved(monkeypatch):
    oversized = {"@context": {}, "padding": "x" * context_module._MAX_CONTEXT_BYTES}
    monkeypatch.setattr(context_module, "_open", _fake_response(oversized))
    url = "https://example.org/ctx.jsonld"
    assert resolve_context(url, fetch=[url]).unresolved == (url,)


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


def test_non_string_non_dict_context_items_are_unresolved():
    result = resolve_context(["https://w3id.org/ro/crate/1.1/context", 5, True])
    assert set(result.unresolved) == {"5", "True"}
    assert 5 not in result.context
    assert True not in result.context


def test_bundled_contexts_load_as_package_data():
    for name in BUNDLED_CONTEXTS.values():
        data = context_module._load_bundled(name)
        assert "@context" in data
