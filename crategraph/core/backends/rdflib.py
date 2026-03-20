"""RDFLib graph backend — SKETCH ONLY, not yet functional.

This module outlines what an RDF-native backend *could* look like.  It is
deliberately incomplete: the mapping from RO-Crate's JSON-LD (which is
often only loosely RDF-compliant) to a clean RDF graph is non-trivial.

Key tensions:

1. **Entity identity.**  The Protocol uses simple string IDs ("#alice").
   RDFLib uses ``URIRef`` or ``BNode``.  We'd need to resolve relative
   ``@id`` values against a base URI — but many real-world crates use
   bare fragment IDs or URL-encoded paths that aren't valid IRIs.

2. **Properties vs triples.**  Our ``Entity.properties`` is a flat dict.
   In RDF every property is a triple ``(subject, predicate, object)``.
   Converting back and forth loses round-trip fidelity for nested
   structures, lists (``@list``), and typed literals.

3. **Reified relationships.**  RO-Crate ``@type: Relationship`` items are
   already a workaround for RDF's lack of edge properties.  Translating
   them into RDF reification (or named graphs) adds a second layer of
   indirection that's hard to query naturally.

4. **Validation gap.**  Many HASS/GLAM crates don't pass strict RDF
   validation — ``null`` values, leading spaces in ``@type``, bare strings
   where ``@id`` refs are expected.  An RDFLib backend would either need
   to silently drop these (losing data) or pre-clean them (hiding errors).

5. **Query power.**  The payoff would be SPARQL support — ``graph.sparql()``
   as an escape hatch for researchers who know RDF.  That's genuinely
   useful but only if the data survives the round-trip intact.

Recommendation: pursue this only after the reader layer is robust enough
to produce clean, validated Entity/Relationship objects.  At that point
the backend can trust its inputs rather than re-validating RDF compliance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rdflib import Graph as RDFGraph
    from rdflib import Namespace, URIRef

    from crategraph.core.models import Entity, Relationship


class RDFLibBackend:
    """Graph backend backed by an rdflib Graph.  NOT YET FUNCTIONAL."""

    def __init__(self, base_uri: str = "http://example.org/") -> None:
        # Deferred import — rdflib is an optional dep (pip install crategraph[rdf]).
        from rdflib import Graph as RDFGraph
        from rdflib import Namespace

        self._graph: RDFGraph = RDFGraph()
        self._ns: Namespace = Namespace(base_uri)
        self._id_to_uri: dict[str, URIRef] = {}

    def _resolve(self, node_id: str) -> URIRef:
        """Turn a string ID into a URIRef.

        This is where the pain lives: fragment IDs, URL-encoded paths,
        and bare strings all need different handling.  A production version
        would need the crate's root ``@id`` as the base for resolution.
        """
        from rdflib import URIRef

        if node_id in self._id_to_uri:
            return self._id_to_uri[node_id]
        # Naive: treat as fragment relative to base.  Real crates will break this.
        uri = URIRef(self._ns[node_id.lstrip("#")])
        self._id_to_uri[node_id] = uri
        return uri

    def add_node(self, node_id: str, entity: Entity) -> None:
        from rdflib import RDF, Literal, URIRef

        uri = self._resolve(node_id)
        # Map @type → rdf:type triples (one per type).
        for t in entity.types:
            self._graph.add((uri, RDF.type, URIRef(self._ns[t])))
        # Flatten properties into literal triples.
        # Problem: @id references become literals instead of URIRef links,
        # nested dicts are lost, lists are unordered.
        for key, value in entity.properties.items():
            if isinstance(value, str):
                self._graph.add((uri, URIRef(self._ns[key]), Literal(value)))
            # TODO: handle @id refs, typed literals, lists

    def add_edge(self, source: str, target: str, key: str, relationship: Relationship) -> None:
        from rdflib import URIRef

        src = self._resolve(source)
        tgt = self._resolve(target)
        predicate = URIRef(self._ns[key])
        self._graph.add((src, predicate, tgt))
        # Reified relationships with properties would need RDF reification
        # or a named-graph approach — neither is straightforward.

    def has_node(self, node_id: str) -> bool:
        if node_id not in self._id_to_uri:
            return False
        uri = self._id_to_uri[node_id]
        return (uri, None, None) in self._graph

    def successors(self, node_id: str) -> set[str]:
        """Nodes this node points to (subject → object triples)."""
        uri = self._resolve(node_id)
        # Reverse-lookup from URIRef back to string ID.
        uri_to_id = {v: k for k, v in self._id_to_uri.items()}
        result: set[str] = set()
        for _s, _p, o in self._graph.triples((uri, None, None)):
            if o in uri_to_id:
                result.add(uri_to_id[o])
        return result

    def predecessors(self, node_id: str) -> set[str]:
        """Nodes that point to this node (object ← subject triples)."""
        uri = self._resolve(node_id)
        uri_to_id = {v: k for k, v in self._id_to_uri.items()}
        result: set[str] = set()
        for s, _p, _o in self._graph.triples((None, None, uri)):
            if s in uri_to_id:
                result.add(uri_to_id[s])
        return result

    # --- The real payoff ---

    def sparql(self, query: str) -> list[dict[str, str]]:
        """Run a SPARQL query against the underlying RDF graph.

        This is the reason you'd want an RDFLib backend at all — direct
        SPARQL for researchers who think in triples.
        """
        raise NotImplementedError("RDFLib backend is a sketch — not yet functional")
