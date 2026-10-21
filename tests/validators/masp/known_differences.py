"""Deliberate differences between the Python MASP validator and the JS one.

Each entry pins one numbered difference from the "Differences from the
JavaScript validator" list to the parity cases where it shows up. The parity
test removes ``js_only`` from the JS results and ``py_only`` from the Python
results of every case whose label matches one of ``cases`` (``fnmatch``
globs), and fails if an entry explains nothing in a case it matches.

Property outcome keys are ``(class_id, entity_id, property_rule_id, passed)``;
cardinality keys are ``(class_id, passed, valid_count)``.
"""

from __future__ import annotations

from dataclasses import dataclass

SPEC_DIFFERENCE_NUMBERS = range(1, 16)


@dataclass(frozen=True)
class KnownDifference:
    number: int
    summary: str
    cases: tuple[str, ...]
    js_only: frozenset[tuple]
    py_only: frozenset[tuple]
    is_valid_flips: bool = False


_DATASET = "#class_Dataset"
_HAS_MEMBER = "#prop_pcdm:hasMember_Dataset"
_AUTHOR = "#prop_author_Dataset"
_COOEE = "arcp://name,corpus-of-oz-early-english"
_F2F = "arcp://name,farms-to-freeways-example-dataset"


KNOWN_DIFFERENCES: list[KnownDifference] = [
    KnownDifference(
        number=9,
        summary=(
            "Properties match by expanded IRI. The RO-Crate context maps `hasMember` to "
            "pcdm:hasMember, so the LDaC rule labelled `pcdm:hasMember` sees it and checks "
            "its members, which fail; the JS looks up the literal key `pcdm:hasMember`, "
            "finds nothing and passes. In f2f the crate's own context maps `author` to an "
            "LDaC term, so it is not schema.org `author` and the required rule fails; the "
            "JS matches the compact key `author` and passes. A root Dataset failing a "
            "property also drops out of the (unbounded) Dataset class count."
        ),
        cases=(
            "batch:ldac-examples-*",
            "batch:paradisec-NT*-ldac",
            "ldac-validator.test.js:109 #*",
            "ldac-validator.test.js:116 #*",
            "ldac-validator.test.js:160 #*",
        ),
        js_only=frozenset(
            {
                (_DATASET, "./", _HAS_MEMBER, True),
                (_DATASET, "/", _HAS_MEMBER, True),
                (_DATASET, _COOEE, _HAS_MEMBER, True),
                (_DATASET, _F2F, _HAS_MEMBER, True),
                (_DATASET, _F2F, _AUTHOR, True),
                (_DATASET, True, 1),
            }
        ),
        py_only=frozenset(
            {
                (_DATASET, "./", _HAS_MEMBER, False),
                (_DATASET, "/", _HAS_MEMBER, False),
                (_DATASET, _COOEE, _HAS_MEMBER, False),
                (_DATASET, _F2F, _HAS_MEMBER, False),
                (_DATASET, _F2F, _AUTHOR, False),
                (_DATASET, True, 0),
            }
        ),
    ),
]
