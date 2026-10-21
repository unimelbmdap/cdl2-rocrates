"""Resolve JSON-LD contexts offline and expand terms to full IRIs.

rdflib's ``Context`` fetches remote context URLs on its own. To keep network
use under the caller's control, :func:`resolve_context` first replaces every
context URL (top level, nested in other contexts, ``@import`` and scoped
contexts) with a bundled copy, or with a fetched copy when ``fetch=True``.
Whatever cannot be resolved is dropped and reported.

:class:`TermExpander` is the only code in crategraph that touches rdflib's
``Context``, which is internal rather than documented API.
"""

from __future__ import annotations

import copy
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from importlib import resources
from typing import Any, NamedTuple

# Context URL -> file name in the ``contexts/`` package data directory. See
# ``contexts/README.md`` for sources and licences. The 1.2-DRAFT URL now
# serves the published 1.2 context byte for byte, so both share one file.
BUNDLED_CONTEXTS: dict[str, str] = {
    "https://w3id.org/ro/crate/1.1/context": "ro-crate-1.1.json",
    "https://w3id.org/ro/crate/1.2/context": "ro-crate-1.2.json",
    "https://w3id.org/ro/crate/1.2-DRAFT/context": "ro-crate-1.2.json",
}

_FETCH_TIMEOUT = 30
_MAX_REDIRECTS = 5
_ACCEPT = "application/ld+json, application/json"
_IMPORT = "@import"
_CONTEXT = "@context"

# Successfully fetched context documents, keyed by URL, for this process.
_FETCH_CACHE: dict[str, Any] = {}

_ABSOLUTE_IRI = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_GUARDED_PREFIXES = ("@", "#", "./", "../", "urn:")


class ContextResolution(NamedTuple):
    """A context with every URL inlined, plus the URLs that could not be."""

    context: list[Any]
    unresolved: tuple[str, ...]


def _lookup_key(url: str) -> str:
    """Normalise a URL so lookups ignore a trailing ``/`` and http vs https."""
    url = url.rstrip("/")
    if url.startswith("https://"):
        url = "http://" + url[len("https://") :]
    return url


_BUNDLED_BY_KEY = {_lookup_key(url): name for url, name in BUNDLED_CONTEXTS.items()}


def _load_bundled(name: str) -> Any:
    path = resources.files("crategraph.validators.masp") / "contexts" / name
    return json.loads(path.read_text(encoding="utf-8"))


def _refused_address(address: str) -> bool:
    """True for an address that is not on the public internet."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    )


def _fetch_allowed(url: str) -> bool:
    """True when *url* is an http(s) URL whose host has only public addresses.

    Crate data chooses the URLs, so fetching must never reach local files or
    loopback, private, link-local or other non-public network addresses. A
    host that does not resolve is refused too.
    """
    try:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
            return False
        host = parts.hostname
        try:
            ipaddress.ip_address(host)
        except ValueError:
            addresses = [info[4][0] for info in socket.getaddrinfo(host, None)]
        else:
            addresses = [host]
    except (OSError, ValueError, UnicodeError):
        return False
    return bool(addresses) and not any(_refused_address(a) for a in addresses)


class _GuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow at most a few redirects, and only to addresses we may fetch."""

    max_redirections = _MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _fetch_allowed(newurl):
            raise urllib.error.HTTPError(newurl, code, "redirect refused", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(request: urllib.request.Request, timeout: float) -> Any:
    opener = urllib.request.build_opener(_GuardedRedirectHandler)
    return opener.open(request, timeout=timeout)


def _fetch(url: str) -> Any | None:
    """Fetch the document at *url*, or return ``None`` on any failure."""
    if url in _FETCH_CACHE:
        return _FETCH_CACHE[url]
    if not _fetch_allowed(url):
        return None
    try:
        request = urllib.request.Request(url, headers={"Accept": _ACCEPT})
        with _open(request, timeout=_FETCH_TIMEOUT) as response:
            document = json.loads(response.read())
    except (OSError, ValueError):
        # URLError, HTTPError (including a refused redirect) and timeouts are
        # OSErrors; a malformed URL or bad JSON is a ValueError.
        return None
    _FETCH_CACHE[url] = document
    return document


class _Resolver:
    def __init__(self, fetch: bool) -> None:
        self._fetch = fetch
        self._unresolved: dict[str, None] = {}

    @property
    def unresolved(self) -> tuple[str, ...]:
        return tuple(self._unresolved)

    def _document_context(self, url: str) -> Any | None:
        """Return the ``@context`` value of the document behind *url*."""
        name = _BUNDLED_BY_KEY.get(_lookup_key(url))
        if name is not None:
            document = _load_bundled(name)
        elif self._fetch:
            document = copy.deepcopy(_fetch(url))
        else:
            document = None
        if not isinstance(document, dict) or _CONTEXT not in document:
            return None
        return document[_CONTEXT]

    def resolve(self, context: Any, base: str | None, active: frozenset[str]) -> list[Any]:
        """Inline *context* (a URL, dict, ``None`` or list of these)."""
        items = context if isinstance(context, list) else [context]
        resolved: list[Any] = []
        for item in items:
            if isinstance(item, str):
                resolved.extend(self._resolve_url(item, base, active))
            elif isinstance(item, dict):
                resolved.append(self._resolve_dict(item, base, active))
            elif item is None:
                if isinstance(context, list):
                    # ``None`` inside a list resets the active context; keep it.
                    resolved.append(item)
            else:
                # Not a URL, an object or null: rdflib cannot use it.
                self._unresolved[repr(item)] = None
        return resolved

    def _resolve_url(self, url: str, base: str | None, active: frozenset[str]) -> list[Any]:
        if base:
            try:
                url = urllib.parse.urljoin(base, url)
            except ValueError:
                # A malformed reference such as ``//[abc/x`` cannot be joined.
                self._unresolved[url] = None
                return []
        if url in active:
            # Already being inlined further up: a cycle, so stop here.
            return []
        inner = self._document_context(url)
        if inner is None:
            self._unresolved[url] = None
            return []
        return self.resolve(inner, url, active | {url})

    def _resolve_dict(
        self, item: dict[str, Any], base: str | None, active: frozenset[str]
    ) -> dict[str, Any]:
        own = {
            key: self._resolve_scoped(value, base, active)
            for key, value in item.items()
            if key != _IMPORT
        }
        imported_url = item.get(_IMPORT)
        if not isinstance(imported_url, str):
            return own
        merged: dict[str, Any] = {}
        for imported in self._resolve_url(imported_url, base, active):
            if isinstance(imported, dict):
                merged.update(imported)
        merged.update(own)
        return merged

    def _resolve_scoped(self, value: Any, base: str | None, active: frozenset[str]) -> Any:
        """Inline the scoped ``@context`` of an expanded term definition."""
        if isinstance(value, dict) and _CONTEXT in value:
            value = dict(value)
            value[_CONTEXT] = self.resolve(value[_CONTEXT], base, active)
        return value


def resolve_context(context: Any, *, fetch: bool = False) -> ContextResolution:
    """Replace every context URL in *context* with the context it names.

    Bundled contexts are used first. Other URLs are fetched only when *fetch*
    is true (and cached for the process); otherwise, or when fetching fails,
    they are dropped and listed in ``unresolved``. Never raises for a
    missing or unreachable context.
    """
    resolver = _Resolver(fetch)
    resolved = resolver.resolve(context, None, frozenset())
    return ContextResolution(resolved, resolver.unresolved)


def normalise_iri(iri: str) -> str:
    """Rewrite ``https://schema.org/`` to ``http://schema.org/``."""
    if iri.startswith("https://schema.org/"):
        return "http://schema.org/" + iri[len("https://schema.org/") :]
    return iri


class TermExpander:
    """Expand compact JSON-LD terms to full IRIs under one resolved context."""

    def __init__(self, context: list[Any]) -> None:
        from rdflib.plugins.shared.jsonld.context import Context

        if any(isinstance(item, str) for item in context):
            msg = "TermExpander needs a context without URLs; pass it through resolve_context."
            raise ValueError(msg)
        self._context = Context(context)
        self._cache: dict[str, str | None] = {}

    def expand(self, term: str) -> str | None:
        """Return the full IRI for *term*, or ``None`` if it does not expand.

        Keywords, relative ids, absolute IRIs and terms with an undefined
        prefix come back unchanged.
        """
        if term not in self._cache:
            self._cache[term] = self._expand(term)
        return self._cache[term]

    def _expand(self, term: str) -> str | None:
        # rdflib would vocab-expand all of these (``@id`` becomes
        # ``http://schema.org/@id``), so they never reach it.
        if term.startswith(_GUARDED_PREFIXES) or _ABSOLUTE_IRI.match(term):
            return term
        if ":" in term and term not in self._context.terms:
            prefix = term.split(":", 1)[0]
            if prefix not in self._context.terms:
                return term
        return self._context.expand(term)
