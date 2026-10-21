"""Parse a MASP profile crate into typed validation rules.

Ports the rule parsing of ``masp-validator.js`` (``parseRules`` and the rule
constructors, plus the class-hierarchy and conformance helpers). Structural
profile keys (``hasPart``, ``sh:minCount``, ``domainIncludes`` and so on) are
read as written, as in the JS; only values that name types or properties are
expanded with the profile's ``@context``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from crategraph.validators.masp.context import normalise_iri
from crategraph.validators.masp.document import CrateDocument, Node, is_reference, literal_of
from crategraph.validators.report import make_row

if TYPE_CHECKING:
    from pathlib import Path

SCHEMA_ROLE = "http://www.w3.org/ns/dx/prof/role/schema"
VOCABULARY_ROLE = "http://www.w3.org/ns/dx/prof/role/vocabulary"
CONFORMANCE_INDICATOR_ROLES = frozenset({"https://w3id.org/ro/conformance-indicators"})
ENUMERATION_IRI = "http://schema.org/Enumeration"

# Compact type name -> expanded IRI; a node matches on either.
_CLASS = ("rdfs:Class", "http://www.w3.org/2000/01/rdf-schema#Class")
_PROPERTY = ("rdf:Property", "http://www.w3.org/1999/02/22-rdf-syntax-ns#Property")
_ITEM_LIST = ("ItemList", "http://schema.org/ItemList")
_PROPERTY_VALUE = ("PropertyValue", "http://schema.org/PropertyValue")
_RESOURCE_DESCRIPTOR = ("ResourceDescriptor", "http://www.w3.org/ns/dx/prof/ResourceDescriptor")
_PROFILE = ("Profile", "http://www.w3.org/ns/dx/prof/Profile")

_SPECIALIZATION_OF = "prov:specializationOf"
_COUNT = re.compile(r"^\s*\d+\s*$")
_WEB_URI = re.compile(r"^https?://", re.IGNORECASE)


@dataclass(frozen=True)
class PropertyRule:
    id: str
    name: str | None
    iri: str | None
    label: str
    min_count: int
    max_count: int | None
    ranges: tuple[str, ...]
    domains: tuple[str, ...]


@dataclass(frozen=True)
class ClassRule:
    id: str
    name: str
    type_iris: frozenset[str]
    min_count: int
    max_count: int | None
    property_rules: tuple[PropertyRule, ...]


@dataclass(frozen=True)
class PropertyValueRule:
    id: str
    values: tuple[Any, ...]
    min_count: int
    max_count: int | None


@dataclass(frozen=True)
class ItemListRule:
    id: str
    elements: tuple[Node | dict, ...]


def _first_string(values: list[Any] | None) -> str | None:
    """The first non-empty string, as JS ``asFirstString`` returns it."""
    for value in values or ():
        if isinstance(value, str) and value:
            return value
    return None


def _ids(values: list[Any] | None) -> list[str]:
    """The ``@id`` of each reference, or each non-empty string, in *values*."""
    out: list[str] = []
    for value in values or ():
        if is_reference(value):
            value = value["@id"]
        if isinstance(value, str) and value:
            out.append(value)
    return out


def _inline_node(item: dict) -> Node:
    raw_type = item.get("@type", [])
    types = raw_type if isinstance(raw_type, list) else [raw_type]
    properties = {
        key: list(value) if isinstance(value, list) else [value]
        for key, value in item.items()
        if key not in ("@id", "@type")
    }
    return Node(
        id=item["@id"],
        types=tuple(t for t in types if isinstance(t, str)),
        properties=properties,
    )


class Profile:
    """A MASP profile crate, parsed into class, property and value rules."""

    def __init__(self, document: CrateDocument) -> None:
        self.source = document.source
        self.document = document
        self.classes: dict[str, ClassRule] = {}
        self.properties: dict[str, PropertyRule] = {}
        self.property_values: dict[str, PropertyValueRule] = {}
        self.item_lists: dict[str, ItemListRule] = {}
        self.warnings: list[dict] = []
        self._item_list_nodes: dict[str, Node] = {}
        self._loose_property_rules: dict[str, PropertyRule] = {}
        self._cycles: dict[str, frozenset[str]] | None = None
        self._summaries: dict[tuple[str, frozenset[str]], tuple[bool, tuple[str, ...]]] = {}
        self._vocabulary_values: dict[str, list[str]] = {}
        self._domain_members: dict[str, list[str]] = {}
        self._parse()

    @classmethod
    def from_json(cls, data: dict, *, source: str, fetch_contexts: bool = False) -> Profile:
        return cls(CrateDocument.from_json(data, source=source, fetch_contexts=fetch_contexts))

    @classmethod
    def load(cls, path: Path, *, fetch_contexts: bool = False) -> Profile:
        return cls(CrateDocument.load(path, fetch_contexts=fetch_contexts))

    # -- parsing -------------------------------------------------------------

    def _warn(self, message: str, entity_id: str | None, rule: str = "profile") -> None:
        self.warnings.append(
            make_row(
                passed=False,
                severity="warning",
                rule=rule,
                entity_id=entity_id,
                property=None,
                message=message,
                source=self.source,
            )
        )

    def _has_type(self, node: Node, kind: tuple[str, str]) -> bool:
        compact, iri = kind
        return compact in node.types or iri in self.document.type_iris(node)

    def _parse(self) -> None:
        for url in self.document.unresolved_contexts:
            self._warn(
                f"Profile context {url} could not be resolved; terms it defines are "
                "compared as written",
                None,
                rule="context",
            )

        root = self.document.root()
        if root is None:
            raise ValueError(f"{self.source}: profile has no root data entity")
        resources = [
            node
            for node in (self.document.get(i) for i in _ids(root.properties.get("hasResource")))
            if node is not None and self._has_type(node, _RESOURCE_DESCRIPTOR)
        ]
        schema = self._descriptor_with_role(resources, SCHEMA_ROLE)
        if schema is None:
            raise ValueError(
                f"{self.source}: profile root has no hasResource ResourceDescriptor "
                f"with the schema role {SCHEMA_ROLE}"
            )

        for node in self.document.nodes.values():
            for domain in dict.fromkeys(
                v["@id"] for v in node.properties.get("domainIncludes", ()) if is_reference(v)
            ):
                self._domain_members.setdefault(domain, []).append(node.id)

        pending_classes: dict[str, ClassRule] = {}
        for node in self._descriptor_parts(schema):
            if node.id in pending_classes or self._rule_known(node.id):
                continue
            if self._has_type(node, _CLASS):
                pending_classes[node.id] = self._class_rule(node)
            elif self._has_type(node, _PROPERTY):
                self.properties[node.id] = self._property_rule(node)
            elif self._has_type(node, _ITEM_LIST):
                self._item_list_nodes[node.id] = node
                self.item_lists[node.id] = self._item_list_rule(node)
            elif self._has_type(node, _PROPERTY_VALUE):
                self.property_values[node.id] = self._property_value_rule(node)
            # DefinedTermSet rules do nothing in the JS, so they are not kept.

        for class_id, rule in pending_classes.items():
            self.classes[class_id] = replace(
                rule, property_rules=self._property_rules_for(class_id)
            )

        vocabulary = self._descriptor_with_role(resources, VOCABULARY_ROLE)
        if vocabulary is not None:
            for node in self._descriptor_parts(vocabulary):
                for type_id in node.types:
                    self._vocabulary_values.setdefault(type_id, []).append(node.id)

    def _rule_known(self, node_id: str) -> bool:
        return (
            node_id in self.properties
            or node_id in self.item_lists
            or node_id in self.property_values
        )

    def _descriptor_with_role(self, resources: list[Node], role: str) -> Node | None:
        """The first ResourceDescriptor among *resources* with *role* (JS l.798-806)."""
        for node in resources:
            if role in _ids(node.properties.get("hasRole")):
                return node
        return None

    def _descriptor_parts(self, descriptor: Node) -> list[Node]:
        """Resolve a descriptor's ``hasPart`` to profile nodes (JS l.766-796).

        A part may be a reference, a plain id string, or a string holding the
        JSON of the parts (some generated crates store ``hasPart`` that way).
        """
        parts: list[Any] = []
        for value in descriptor.properties.get("hasPart", ()):
            if isinstance(value, str):
                try:
                    decoded = json.loads(value)
                except ValueError:
                    decoded = None
                if isinstance(decoded, (list, dict)):
                    parts.extend(decoded if isinstance(decoded, list) else [decoded])
                    continue
            parts.append(value)

        nodes: list[Node] = []
        for part in parts:
            if isinstance(part, str) and part:
                nodes.append(self.document.get(part) or Node(id=part, types=(), properties={}))
            elif is_reference(part) and isinstance(part["@id"], str):
                nodes.append(self.document.get(part["@id"]) or _inline_node(part))
        return nodes

    def _count(self, node: Node, key: str) -> int | None:
        """Parse a cardinality; ``None`` means absent or invalid (use the default)."""
        values = node.properties.get(key)
        if not values:
            return None
        raw = values[0]
        value = literal_of(raw)
        if isinstance(value, bool):
            pass
        elif isinstance(value, int):
            if value >= 0:
                return value
        elif isinstance(value, float):
            if value.is_integer() and value >= 0:
                return int(value)
        elif isinstance(value, str) and _COUNT.match(value):
            return int(value)
        self._warn(f"Rule {node.id}: ignoring invalid {key} {raw!r}", node.id)
        return None

    def _class_rule(self, node: Node) -> ClassRule:
        """Build a class rule without its property rules (JS l.132-153)."""
        if _SPECIALIZATION_OF in node.properties:
            raw_types = _ids(node.properties[_SPECIALIZATION_OF])
        else:
            raw_types = [node.id]
        expander = self.document.expander
        type_iris = frozenset(normalise_iri(expander.expand(t) or t) for t in raw_types)
        if not type_iris:
            self._warn(
                f"Class rule {node.id} does not specify any types via prov:specializationOf",
                node.id,
            )
        return ClassRule(
            id=node.id,
            name=(
                _first_string(node.properties.get("name"))
                or _first_string(node.properties.get("rdfs:label"))
                or node.id
            ),
            type_iris=type_iris,
            min_count=self._count(node, "sh:minCount") or 0,
            max_count=self._count(node, "sh:maxCount"),
            property_rules=(),
        )

    def _property_rule(self, node: Node) -> PropertyRule:
        """Build a property rule (JS l.329-343)."""
        props = node.properties
        name = _first_string(props.get("rdfs:label")) or _first_string(props.get("name"))
        iri = None
        if name is None:
            self._warn(f"Property rule {node.id} does not have a name", node.id)
        elif name != "@id":
            expanded = self.document.expander.expand(name)
            iri = None if expanded is None else normalise_iri(expanded)
        if "rangeIncludes" in props:
            ranges = props["rangeIncludes"]
        else:
            ranges = props.get("http://schema.org/rangeIncludes", [])
        return PropertyRule(
            id=node.id,
            name=name,
            iri=iri,
            label=_first_string(props.get("name"))
            or _first_string(props.get("rdfs:label"))
            or node.id,
            min_count=self._count(node, "sh:minCount") or 0,
            max_count=self._count(node, "sh:maxCount"),
            ranges=tuple(_ids(ranges)),
            domains=tuple(_ids(props.get("domainIncludes"))),
        )

    def _property_value_rule(self, node: Node) -> PropertyValueRule:
        """Build a PropertyValue rule (JS l.827-834)."""
        return PropertyValueRule(
            id=node.id,
            values=tuple(node.properties.get("value", ())),
            min_count=self._count(node, "sh:minCount") or 0,
            max_count=self._count(node, "sh:maxCount"),
        )

    def _item_list_rule(self, node: Node) -> ItemListRule:
        """Build an item list rule, resolving referenced elements (JS l.550-553)."""
        elements: list[Node | dict] = []
        for element in node.properties.get("itemListElement", ()):
            if is_reference(element):
                elements.append(self.document.get(element["@id"]) or element)
            elif isinstance(element, dict):
                elements.append(element)
        return ItemListRule(id=node.id, elements=tuple(elements))

    def _property_rules_for(self, class_id: str) -> tuple[PropertyRule, ...]:
        """Own property rules, then inherited ones, de-duplicated (JS l.287-322).

        As in the JS, every profile entity whose ``domainIncludes`` names the
        class (or an ancestor) becomes a property rule, whether or not the
        schema descriptor lists it.
        """
        rules: dict[str, PropertyRule] = {}
        for owner in (class_id, *self.ancestor_class_ids(class_id)):
            for member_id in self._domain_members.get(owner, ()):
                if member_id not in rules:
                    rules[member_id] = self._property_rule_by_id(member_id)
        return tuple(rules.values())

    def _property_rule_by_id(self, node_id: str) -> PropertyRule:
        if node_id in self.properties:
            return self.properties[node_id]
        if node_id not in self._loose_property_rules:
            node = self.document.get(node_id)
            assert node is not None  # ids come from the document's own nodes
            self._loose_property_rules[node_id] = self._property_rule(node)
        return self._loose_property_rules[node_id]

    # -- class hierarchy -----------------------------------------------------

    def _parent_class_ids(self, class_id: str) -> list[str]:
        """Immediate ``rdfs:subClassOf`` ids (JS ``getParentClassIds``, l.1537-1545)."""
        node = self.document.get(class_id)
        if node is None:
            return []
        return _ids(node.properties.get("rdfs:subClassOf"))

    def _cycle_members(self) -> dict[str, frozenset[str]]:
        """Each class in an ``rdfs:subClassOf`` cycle, mapped to its whole cycle.

        Precisely: the strongly connected components with more than one class.
        """
        if self._cycles is None:
            import networkx as nx

            graph = nx.DiGraph()
            for node in self.document.nodes.values():
                graph.add_edges_from((node.id, p) for p in self._parent_class_ids(node.id))
            self._cycles = {
                member: frozenset(component)
                for component in nx.strongly_connected_components(graph)
                if len(component) > 1
                for member in component
            }
        return self._cycles

    def _ancestor_summary(
        self, class_id: str, visited: frozenset[str]
    ) -> tuple[bool, tuple[str, ...]]:
        """Summarise the JS ``parentClasses`` paths (l.1560-1576) without listing them.

        The JS lists every ancestor path from *class_id* up to a root class; a
        path that runs back into a class already on it yields no path at all.
        Returns whether any path survives, and the classes on the surviving
        paths in first-seen order (``dict.fromkeys`` over the concatenated
        paths). Memoised on the class and the visited classes in its own
        cycle, the only ones that can affect the result, so outside
        ``rdfs:subClassOf`` cycles the work grows with the number of classes
        rather than the number of paths.
        """
        if class_id in visited:
            return False, ()
        key = (class_id, visited & self._cycle_members().get(class_id, frozenset()))
        if key not in self._summaries:
            parents = self._parent_class_ids(class_id)
            if not parents:
                summary: tuple[bool, tuple[str, ...]] = (True, ())
            else:
                inner = visited | {class_id}
                alive = False
                order: dict[str, None] = {}
                for parent in parents:
                    parent_alive, parent_order = self._ancestor_summary(parent, inner)
                    if parent_alive:
                        alive = True
                        order[parent] = None
                        order.update(dict.fromkeys(parent_order))
                summary = (alive, tuple(order))
            self._summaries[key] = summary
        return self._summaries[key]

    def ancestor_class_ids(self, class_id: str) -> list[str]:
        """All ancestor class ids, nearest first, de-duplicated (JS l.1583-1585)."""
        return list(self._ancestor_summary(class_id, frozenset())[1])

    def is_enumeration_class(self, class_id: str) -> bool:
        """True for ``schema.org/Enumeration`` or any subclass of it (JS l.1593-1597)."""
        return any(
            normalise_iri(c) == ENUMERATION_IRI
            for c in (class_id, *self.ancestor_class_ids(class_id))
        )

    def enumeration_value_ids(self, class_id: str) -> frozenset[str]:
        """Allowed ids for an enumeration class (JS l.917-936, then l.1605-1615).

        The vocabulary descriptor's values for that type come first; failing
        those, every profile entity typed with the class.
        """
        if class_id in self._vocabulary_values:
            return frozenset(self._vocabulary_values[class_id])
        return frozenset(
            node.id for node in self.document.nodes.values() if class_id in node.types
        )

    # -- conformance ---------------------------------------------------------

    @staticmethod
    def _web_uri(entity_id: str | None) -> str | None:
        """JS ``resolveProfileEntityUri`` with no base URL set (l.1154-1169)."""
        if entity_id and _WEB_URI.match(entity_id):
            return entity_id
        return None

    def _conformance_indicator_uris(self) -> list[str]:
        """Port of ``getConformanceIndicatorUris`` (JS l.1224-1278)."""
        uris: dict[str, None] = {}
        for node in self.document.nodes.values():
            if not self._has_type(node, _RESOURCE_DESCRIPTOR):
                continue
            if not CONFORMANCE_INDICATOR_ROLES.intersection(_ids(node.properties.get("hasRole"))):
                continue
            for artifact_id in _ids(node.properties.get("hasArtifact")):
                artifact = self.document.get(artifact_id)
                if artifact is not None and self._has_type(artifact, _ITEM_LIST):
                    for entry_id in _ids(artifact.properties.get("itemListElement")):
                        uris[self._web_uri(entry_id) or entry_id] = None
                    continue
                uris[self._web_uri(artifact_id) or artifact_id] = None
        return list(uris)

    def _profile_conforms_to_entity(self) -> Node | None:
        """Port of ``getProfileConformsToEntity`` (JS l.1171-1222).

        Only reached when there are no conformance indicators, so the JS's
        first loop over them is left out.
        """
        for rule_id in self.item_lists:
            node = self._item_list_nodes[rule_id]
            name = _first_string(node.properties.get("name")) or ""
            if "conformsto" not in node.id.lower() and "conformsto" not in name.lower():
                continue
            for element_id in _ids(node.properties.get("itemListElement")):
                candidate = self.document.get(element_id)
                if candidate is not None and self._has_type(candidate, _PROFILE):
                    return candidate
        root = self.document.root()
        if root is not None and self._has_type(root, _PROFILE):
            return root
        for node in self.document.nodes.values():
            if self._has_type(node, _PROFILE):
                return node
        return None

    def _profile_uri(self) -> str | None:
        """Port of ``getProfileUri`` (JS l.1336-1357)."""
        indicators = self._conformance_indicator_uris()
        if indicators:
            return indicators[0]
        entity = self._profile_conforms_to_entity()
        resolved = self._web_uri(entity.id if entity is not None else None)
        if resolved:
            return resolved
        root = self.document.root()
        return self._web_uri(root.id if root is not None else None)

    def accepted_conformance_uris(self) -> tuple[str, ...]:
        """URIs a crate may name in ``conformsTo`` to claim this profile.

        The conformance-indicator URIs, or failing those the profile URI, as
        JS ``getConformsToUris`` gives them without editor hints.
        """
        uris = self._conformance_indicator_uris()
        if uris:
            return tuple(uris)
        profile_uri = self._profile_uri()
        return (profile_uri,) if profile_uri else ()
