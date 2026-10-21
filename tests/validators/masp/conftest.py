"""Shared builders for MASP validator tests."""

from __future__ import annotations

DEFAULT_CONTEXT = [
    "https://w3id.org/ro/crate/1.2/context",
    {"@vocab": "http://schema.org/"},
]


def _wrap(entities: tuple[dict, ...], context, root: dict, conforms: str | None = None) -> dict:
    descriptor = {
        "@id": "ro-crate-metadata.json",
        "@type": "CreativeWork",
        "about": {"@id": "./"},
        "conformsTo": {"@id": "https://w3id.org/ro/crate/1.2"},
    }
    return {
        "@context": list(DEFAULT_CONTEXT) if context is None else context,
        "@graph": [descriptor, root, *entities],
    }


def make_crate(*entities: dict, context=None, root: dict | None = None) -> dict:
    """Build a minimal crate with a descriptor and root dataset."""
    root_entity = (
        root if root is not None else {"@id": "./", "@type": "Dataset", "name": "Test crate"}
    )
    return _wrap(entities, context, root_entity)


def make_profile(*rules: dict, context=None, root_extra: dict | None = None) -> dict:
    """Build a MASP profile whose ResourceDescriptor lists every rule."""
    descriptor_id = "#profile-descriptor"
    root = {
        "@id": "./",
        "@type": "Dataset",
        "name": "Test profile",
        "hasPart": [{"@id": descriptor_id}],
        **(root_extra or {}),
    }
    resource = {
        "@id": descriptor_id,
        "@type": "ResourceDescriptor",
        "hasPart": [{"@id": r["@id"]} for r in rules],
    }
    return _wrap((resource, *rules), context, root)
