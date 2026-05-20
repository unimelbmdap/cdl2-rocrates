"""Shared property-merge convention for native record exports.

Both :mod:`crategraph.core.records` (``entity_records`` /
``relationship_records``) and :mod:`crategraph.core.text`
(``text_records`` ``include_properties``) copy entity/relationship
properties into a record dict using the same rule: deep-copy the value,
and prefix any name that collides with an already-taken key with
``prop_`` (repeatedly) until unique. This module is the single home for
that rule so the two call sites cannot drift.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from typing import Any


def merge_properties(
    record: dict[str, Any],
    properties: dict[str, Any],
    keys: Iterable[str],
    *,
    reserved: frozenset[str] = frozenset(),
) -> None:
    """Merge the named *keys* of *properties* into *record* in place.

    *keys* must already be in the desired emission order — callers own
    the ordering policy (alphabetical, collisions-last, explicit
    allowlist, …). A name that collides with an existing *record* key or
    a *reserved* name is prefixed with ``prop_`` repeatedly until unique.
    Keys absent from *properties* are skipped. Values are deep-copied so
    callers can mutate the returned record without touching the source.
    """
    taken: set[str] = set(record) | reserved
    for key in keys:
        if key not in properties:
            continue
        out_key = key
        while out_key in taken:
            out_key = f"prop_{out_key}"
        record[out_key] = copy.deepcopy(properties[key])
        taken.add(out_key)
