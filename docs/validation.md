# Validating Against a Profile

A [MASP profile](https://github.com/Language-Research-Technology/ro-crate-masp) (Metadata Application Schema Profile) is itself an RO-Crate. It describes the classes a crate should contain, which properties each class needs, how many values they may have and what kinds of value they take. crategraph can check a crate against such a profile and give you a table of what passed and what did not.

## Install and call

```bash
python -m pip install "crategraph[validate]"
```

```python
from crategraph import Crate

crate = Crate("path/to/my-collection/")
report = crate.validate("path/to/profile/")
report
```

The profile can be a directory containing `ro-crate-metadata.json` or the file itself. Profiles must be local paths.

Validation never touches the network unless you ask it to, and even then it only downloads contexts from a short list, never URLs chosen by the crate (see [Bundled contexts](#bundled-contexts)).

!!! note "It checks the file on disk, not the graph"
    Validation reads the raw `ro-crate-metadata.json` the crate was loaded from. Filtering, selecting or transforming the graph does not change the result, and a graph that was not loaded from an RO-Crate cannot be validated. A derived graph validates the full source crate (or crates, for a combined graph).

## Reading the report

The report is a table with one row per check. Errors come first, then warnings, info rows and passes.

| Column | Meaning |
| --- | --- |
| `severity` | `error`, `warning` or `info` for a failed check; `None` for a pass |
| `passed` | `True` or `False` |
| `rule` | The profile rule checked, or `context`, `duplicate-id`, `conformance` or `profile` for checks on the crate and profile themselves |
| `entity_id` | The entity the row is about, if any |
| `property` | The property the row is about, if any |
| `message` | A plain-language explanation |
| `source` | The metadata file the row came from (useful when validating several crates at once) |

```python
report.is_valid                      # False if there is at least one error
report.counts()                      # {'error': 2, 'warning': 1, 'info': 4, 'passed': 37}

import pandas as pd
df = pd.DataFrame(report)
df[~df.passed]                       # everything that did not pass
df[df.severity == "error"]           # just the errors
```

`is_valid` is `True` unless there is at least one `error` row. Warnings and info rows never make a crate invalid.

`info` rows give the detail behind an error. When a class needs at least one instance and none qualifies, the error names each near miss and why it failed, for example ``./: property `license`: missing required property``. The per-property failures behind it appear as `info` rows. A separate `info` row reports whether the crate claims conformance to the profile (through `conformsTo` on the root entity or the metadata descriptor). This is informational because real crates often cite older or sibling profile URIs.

Malformed profiles, unreadable crates and graphs that did not come from an RO-Crate raise an exception (`ValueError`, `FileNotFoundError` or `TypeError`) rather than producing a row.

## Bundled contexts

JSON-LD contexts tell the validator what each property name means, so that a crate using `author` and a profile asking for `schema:author` can be matched. These contexts are bundled and work offline: RO-Crate 1.1, 1.2 and 1.2-DRAFT (all CC0).

The two Language Data Commons (LDaC) contexts are **not** bundled: `http://purl.archive.org/language-data-commons/context.json` and `https://w3id.org/ldac/context`. The only licence we could find for them is GPL-3.0, which crategraph cannot redistribute. Offline, a crate that uses an LDaC context gets a `context` warning saying the context could not be resolved, and terms defined only by that context cannot be matched. Pass `fetch_contexts=True` to download them for the run:

```python
report = crate.validate("path/to/ldac-profile/", fetch_contexts=True)
```

`fetch_contexts=True` only downloads the two LDaC contexts above. Any other context URL in a crate or profile stays unresolved, because a crate downloaded from the internet should not be able to make your computer contact an address of its choosing. To allow another context, list its URL; the LDaC contexts stay allowed:

```python
report = crate.validate(
    "path/to/profile/",
    fetch_contexts=["https://example.org/my-community/context.jsonld"],
)
```

Fetched contexts are cached for the rest of the Python session. Even for allowed URLs, only `http` and `https` addresses on the public internet are fetched: hosts that resolve to private or local network addresses (loopback, private ranges, link-local and similar) are refused, the same check applies to every redirect, at most five redirects are followed, and a context larger than 2 MB is ignored. A context that is not allowed or cannot be fetched is reported as unresolved, and the warning says how to allow it.

## Differences from the JavaScript validator

crategraph's validator is a Python port of the [ro-crate-masp](https://github.com/Language-Research-Technology/ro-crate-masp) validator and was checked against the JavaScript results on a corpus of profile and crate pairs. The two agree except for the following deliberate differences.

| # | Topic | Python behaviour | JavaScript behaviour |
| --- | --- | --- | --- |
| 1 | A class has too few instances | The error explains each candidate that matched the types but failed, and why | Reports only "expected at least 1, found 0" |
| 2 | Too many values | An `error` that names the entity and property | An `error` with no entity |
| 3 | Number range | Accepts JSON numbers and numeric strings | Also accepts `""`, whitespace and booleans |
| 4 | Entities that refer to each other | Terminates; a pair already being checked is assumed to pass, and results do not depend on traversal order | Can recurse forever |
| 5 | Malformed profile or unreadable crate | Raises an exception; a profile with no root or no schema `ResourceDescriptor` raises `ValueError` | Returns an error result with rule `exception`, or silently yields zero rules |
| 6 | Conformance claim | New `info` row checking `conformsTo` against the profile and its conformance indicators | Not checked |
| 7 | Regular expressions | `/pattern/flags` is translated to Python: `i`, `m`, `s` apply, `g`, `y`, `u` are ignored, other flags warn. Python's `\w` and `\d` are Unicode-aware, and `$` also matches before a trailing newline | JavaScript regular expression semantics |
| 8 | URL validity | Uses the `validators` package | Uses the WHATWG `URL` parser, so edge cases may differ |
| 9 | Property matching | By expanded IRI, so a key matches however the crate's context spells it (see below) | By compact string, ignoring `@vocab` |
| 10 | Context that cannot be resolved | A `context` warning row | Silently dropped |
| 11 | Duplicate `@id` | One `warning` row per id; values of the duplicates are merged and validated | Not reported |
| 12 | External IRI references | A reference such as `{"@id": "https://creativecommons.org/licenses/by/4.0/"}` with no entity in the crate satisfies a range that includes `URL`, if its `@id` is an `http` or `https` URL that passes the same check as a `URL` value; a malformed one such as `http://[` or a dangling relative id still fails | Fails as "references an entity that does not exist" |
| 13 | Impossible dates and times | `2024-13-01`, `2023-02-29` and timezone offsets out of range (`+24:00`, `+10:60`) fail | Accepted if they fit the pattern |
| 14 | Empty values | A required property given as `[]`, `null` or `""` counts as missing | An empty array satisfies a minimum count |
| 15 | `0` and `false` | Count as values | Treated as missing |

**Difference 9 cuts both ways.** A crate that writes `rightsHolder` while its context maps it to `dct:rightsHolder` now satisfies a rule for `dct:rightsHolder`. Matching also treats `http://` and `https://` schema.org IRIs as the same thing (for example `Enumeration`). But a crate's own context can remap a key away from the IRI a rule expects, in which case the rule is no longer satisfied. The RO-Crate 1.2 context maps `hasMember` to `pcdm:hasMember`, so `hasMember` values are now checked against rules for `pcdm:hasMember`, where the JavaScript validator never saw them.

### Other notes

- A property rule with no name produces one warning per rule.
- A class rule with no types (no `prov:specializationOf`) produces a warning.
- A malformed `sh:minCount` or `sh:maxCount` produces a warning and falls back to the default.
- Literal ranges are matched against both the expanded range IRI and the range name as written (as the JavaScript validator does), so a profile that remaps a bare range name such as `Text` in its own context still accepts values of the original schema.org type.

## Known limitations

- Inheritance (`rdfs:subClassOf`) applies to property rules only; an entity of a subclass is not counted as an instance of the parent class.
- `DefinedTermSet` vocabularies are not checked.
- There are no domain checks and no checks for undeclared properties.
- Profiles must be local paths, not URLs.
- Scoped contexts are not applied. When a term definition in the crate's or profile's context has its own `@context` (a type-scoped or property-scoped context), or an entity in `@graph` carries its own `@context`, terms are still matched using the top-level context only, and the report has one `context` warning for that crate or profile saying so.
- To stop a malformed or hostile file from tying up your computer, some structures are refused with an error naming the file: a `@context` nested more than 32 levels deep or referring to other contexts more than 100 times, and a profile whose `rdfs:subClassOf` hierarchy is more than 100 classes deep or whose subclass cycles are too tangled to evaluate. Real crates and profiles come nowhere near these limits.

Contributors can regenerate the JavaScript comparison corpus with the harness in `scripts/masp-parity/`.
