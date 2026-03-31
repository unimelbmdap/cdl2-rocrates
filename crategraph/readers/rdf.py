"""RDF reader — loads any RDF serialisation via rdflib.

Supports Turtle, RDF/XML, JSON-LD, N-Triples, and other formats
recognised by rdflib. Preserves full URIs, namespace maps, and
literal metadata for round-trip fidelity.
"""

from __future__ import annotations

import warnings  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import Any

from rdflib import DCTERMS, FOAF, RDF, RDFS, XSD, BNode, Literal, Namespace, URIRef  # noqa: F401
from rdflib import Graph as RdfGraph  # noqa: F401
from rdflib.term import Node

from crategraph.core.graph import Graph
from crategraph.core.interfaces import Reader
from crategraph.core.models import Entity, Relationship  # noqa: F401

# XSD types that map directly to Python primitives.
_XSD_INT_TYPES = {
    XSD.integer,
    XSD.int,
    XSD.long,
    XSD.short,
    XSD.byte,
    XSD.nonNegativeInteger,
    XSD.positiveInteger,
    XSD.nonPositiveInteger,
    XSD.negativeInteger,
    XSD.unsignedInt,
    XSD.unsignedLong,
    XSD.unsignedShort,
    XSD.unsignedByte,
}
_XSD_FLOAT_TYPES = {XSD.float, XSD.double, XSD.decimal}
_XSD_BOOL_TYPES = {XSD.boolean}
_XSD_STRING_TYPES = {XSD.string, XSD.normalizedString, XSD.token}

# Well-known namespace for xsd: CURIE prefix in datatype values.
_XSD_NS = str(XSD)

_RDF_EXTENSIONS = {".ttl", ".rdf", ".owl", ".xml", ".nt", ".nq", ".jsonld", ".trig"}

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
DC = Namespace("http://purl.org/dc/elements/1.1/")

_DEFAULT_LABEL_PREDICATES: list[URIRef] = [
    RDFS.label,
    SKOS.prefLabel,
    FOAF.name,
    DCTERMS.title,
    DC.title,
]


class RdfReader(Reader):
    """Read any RDF file into a crategraph Graph."""

    def __init__(
        self,
        *,
        format: str | None = None,
        label_predicates: list[URIRef] | None = None,
        exclude_predicates: list[str] | None = None,
        include_dangling_targets: bool = False,
    ) -> None:
        self._format = format
        self._label_predicates = label_predicates
        self._exclude_predicates = set(exclude_predicates or [])
        self._include_dangling_targets = include_dangling_targets

    # --- Public API (Reader ABC) ---

    def can_read(self, path: str) -> bool:
        raise NotImplementedError

    def read(self, path: str) -> Graph:
        raise NotImplementedError

    # --- URI helpers (static, tested directly) ---

    @staticmethod
    def _to_curie(uri: str, namespaces: dict[str, str]) -> str:
        """Shorten a full URI to CURIE form using a namespace map.

        Returns the CURIE if a prefix matches, otherwise the full URI.
        Never returns a bare local name — this ensures every key is
        reversible to a full URI.
        """
        for prefix, ns_uri in namespaces.items():
            if uri.startswith(ns_uri):
                local = uri[len(ns_uri) :]
                if local:
                    return f"{prefix}:{local}"
        return uri

    @staticmethod
    def _node_id(node: Node) -> str:
        """Return a consistent string ID for an RDF node.

        URIRefs → full URI string.  BNodes → ``_:`` prefix + rdflib ID.
        """
        if isinstance(node, BNode):
            return f"_:{node}"
        return str(node)

    # --- Literal conversion ---

    @staticmethod
    def _convert_literal(literal: Literal) -> Any:
        """Convert an rdflib Literal to a Python value.

        Plain strings and common XSD types (integer, float, boolean) are
        returned as native Python types.  Language-tagged literals return
        ``{"value": ..., "lang": ...}``.  Other typed literals return
        ``{"value": ..., "datatype": ...}`` with the datatype as a CURIE.
        """
        # Language-tagged literal.
        if literal.language:
            return {"value": str(literal), "lang": literal.language}

        dt = literal.datatype

        # No datatype or xsd:string — return plain string.
        if dt is None or dt in _XSD_STRING_TYPES:
            return str(literal)

        # Integer types.
        if dt in _XSD_INT_TYPES:
            return int(literal)

        # Float types.
        if dt in _XSD_FLOAT_TYPES:
            return float(literal)

        # Boolean.
        if dt in _XSD_BOOL_TYPES:
            return literal.toPython()

        # Everything else — preserve datatype as CURIE.
        dt_str = str(dt)
        dt_curie = "xsd:" + dt_str[len(_XSD_NS) :] if dt_str.startswith(_XSD_NS) else dt_str
        return {"value": str(literal), "datatype": dt_curie}
