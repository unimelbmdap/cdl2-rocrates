"""RDF reader — loads any RDF serialisation via rdflib.

Supports Turtle, RDF/XML, JSON-LD, N-Triples, and other formats
recognised by rdflib. Preserves full URIs, namespace maps, and
literal metadata for round-trip fidelity.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

from rdflib import DCTERMS, FOAF, RDF, RDFS, XSD, BNode, Literal, Namespace, URIRef
from rdflib import Graph as RdfGraph
from rdflib.term import Node

from crategraph.core.graph import Graph
from crategraph.core.interfaces import Reader
from crategraph.core.models import Entity, Relationship

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
        """Return True if *path* is an RDF file or directory containing one."""
        p = Path(path)
        if p.is_file():
            return p.suffix.lower() in _RDF_EXTENSIONS
        if p.is_dir():
            return any(f.suffix.lower() in _RDF_EXTENSIONS for f in p.iterdir() if f.is_file())
        return False

    def read(self, path: str) -> Graph:
        """Read the RDF file or directory at *path* and return a populated Graph."""
        p = Path(path)
        rdf = RdfGraph()

        if p.is_dir():
            rdf_files = sorted(
                f for f in p.iterdir() if f.is_file() and f.suffix.lower() in _RDF_EXTENSIONS
            )
            for f in rdf_files:
                rdf.parse(str(f), format=self._format)
            source = str(p.resolve())
            formats = {self._detect_format(str(f)) for f in rdf_files} - {None}
            detected_format = formats.pop() if len(formats) == 1 else "mixed" if formats else None
        else:
            rdf.parse(str(p), format=self._format)
            source = str(p.resolve())
            detected_format = self._detect_format(str(p))

        namespaces = {
            prefix: str(uri)
            for prefix, uri in rdf.namespaces()
            if prefix  # skip the default empty prefix
        }

        graph = Graph(
            source=source,
            metadata={
                "namespaces": namespaces,
                "format": self._format or detected_format,
                "base_uri": None,
            },
        )

        # Collect all subjects that appear in the data.
        subjects = set(rdf.subjects())

        # First pass: build entities from subjects.
        for subject in subjects:
            entity = self._build_entity(subject, rdf, namespaces, source)
            graph._add_node(entity)

        # Second pass: build relationships and track dangling targets.
        existing_ids = {e.id for e in graph.entities}
        relationships: list[Relationship] = []
        dangling_uris: set[str] = set()
        dangling_rel_count = 0

        for subject in subjects:
            source_id = self._node_id(subject)
            for pred, obj in rdf.predicate_objects(subject):
                if pred == RDF.type:
                    continue
                pred_str = str(pred)
                if pred_str in self._exclude_predicates:
                    continue
                if isinstance(obj, (URIRef, BNode)):
                    target_id = self._node_id(obj)
                    rel = Relationship(
                        source=source_id,
                        target=target_id,
                        type=self._to_curie(pred_str, namespaces),
                    )
                    if target_id in existing_ids:
                        relationships.append(rel)
                    elif self._include_dangling_targets:
                        dangling_uris.add(target_id)
                        relationships.append(rel)
                    else:
                        dangling_uris.add(target_id)
                        dangling_rel_count += 1

        # Create stub entities for dangling targets when requested.
        if self._include_dangling_targets:
            for uri in dangling_uris:
                graph._add_node(
                    Entity(id=uri, types=[], properties={"_external": True}, source=source)
                )

        # Emit warning about dropped dangling relationships.
        if not self._include_dangling_targets and dangling_rel_count > 0:
            graph.metadata["dropped_dangling_count"] = dangling_rel_count
            warnings.warn(
                f"Dropped {dangling_rel_count} relationship(s) to "
                f"{len(dangling_uris)} undefined target URI(s).",
                stacklevel=2,
            )

        # Add relationships (after stubs exist).
        for rel in relationships:
            graph._add_edge(rel)

        return graph

    # --- Entity construction helpers ---

    def _build_entity(
        self,
        subject: Node,
        rdf: RdfGraph,
        namespaces: dict[str, str],
        source: str,
    ) -> Entity:
        """Build an Entity from all triples about *subject*."""
        subject_str = self._node_id(subject)

        types: list[str] = []
        type_uris: list[str] = []
        properties: dict[str, Any] = {}

        for pred, obj in rdf.predicate_objects(subject):
            pred_str = str(pred)

            if pred_str in self._exclude_predicates:
                continue

            # rdf:type -> types list (as CURIEs).
            if pred == RDF.type:
                type_uri = str(obj)
                type_uris.append(type_uri)
                types.append(self._to_curie(type_uri, namespaces))
                continue

            # Skip URI-valued predicates — handled as relationships.
            if isinstance(obj, (URIRef, BNode)):
                continue

            # Literal-valued predicate -> property.
            if isinstance(obj, Literal):
                key = self._to_curie(pred_str, namespaces)
                value = self._convert_literal(obj)
                # Accumulate multiple values as a list.
                if key in properties:
                    existing = properties[key]
                    if isinstance(existing, list):
                        existing.append(value)
                    else:
                        properties[key] = [existing, value]
                else:
                    properties[key] = value

        # Store full type URIs for round-trip fidelity.
        if type_uris:
            properties["_type_uris"] = type_uris

        # Resolve display name.
        name = self._resolve_name(properties, namespaces)
        if name is not None:
            properties["name"] = name

        return Entity(id=subject_str, types=types, properties=properties, source=source)

    def _resolve_name(self, properties: dict[str, Any], namespaces: dict[str, str]) -> str | None:
        """Pick the best display name from label-like properties.

        Tie-break: un-tagged -> 'en' -> lexicographic lang -> lexicographic value.
        """
        label_preds = (
            _DEFAULT_LABEL_PREDICATES if self._label_predicates is None else self._label_predicates
        )
        for label_pred in label_preds:
            label_key = self._to_curie(str(label_pred), namespaces)
            if label_key not in properties:
                continue
            raw = properties[label_key]
            candidates = raw if isinstance(raw, list) else [raw]
            return self._pick_best_label(candidates)
        return None

    @staticmethod
    def _pick_best_label(candidates: list[Any]) -> str | None:
        """Select the best label from a list of literal values.

        Priority: plain string -> lang 'en' -> lowest lang tag -> lowest value.
        """
        plain: list[str] = []
        en: list[str] = []
        tagged: list[tuple[str, str]] = []  # (lang, value)

        for c in candidates:
            if isinstance(c, str):
                plain.append(c)
            elif isinstance(c, dict) and "value" in c:
                if "lang" in c:
                    if c["lang"] == "en":
                        en.append(c["value"])
                    else:
                        tagged.append((c["lang"], c["value"]))
                else:
                    # Typed literal without lang — treat as plain.
                    plain.append(str(c["value"]))
            elif isinstance(c, (int, float, bool)):
                plain.append(str(c))

        if plain:
            return sorted(plain)[0]
        if en:
            return sorted(en)[0]
        if tagged:
            tagged.sort()
            return tagged[0][1]
        return None

    @staticmethod
    def _detect_format(path: str) -> str | None:
        """Guess RDF format from file extension."""
        suffix = Path(path).suffix.lower()
        return {
            ".ttl": "turtle",
            ".rdf": "xml",
            ".owl": "xml",
            ".xml": "xml",
            ".nt": "nt",
            ".nq": "nquads",
            ".jsonld": "json-ld",
            ".trig": "trig",
        }.get(suffix)

    # --- URI helpers (static, tested directly) ---

    @staticmethod
    def _to_curie(uri: str, namespaces: dict[str, str]) -> str:
        """Shorten a full URI to CURIE form using a namespace map.

        Returns the CURIE if a prefix matches, otherwise the full URI.
        Never returns a bare local name — this ensures every key is
        reversible to a full URI.  When multiple prefixes match, the
        longest (most specific) namespace URI wins.
        """
        best_prefix: str | None = None
        best_ns: str = ""
        for prefix, ns_uri in namespaces.items():
            if uri.startswith(ns_uri) and len(ns_uri) > len(best_ns):
                local = uri[len(ns_uri) :]
                if local:
                    best_prefix = prefix
                    best_ns = ns_uri
        if best_prefix is not None:
            return f"{best_prefix}:{uri[len(best_ns) :]}"
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
