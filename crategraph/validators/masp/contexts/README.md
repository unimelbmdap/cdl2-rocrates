# Bundled JSON-LD contexts

These context documents ship with crategraph so the MASP validator can expand
terms without network access. Each file is stored byte for byte as fetched on
2026-10-21 with `Accept: application/ld+json, application/json`. The URL to
file mapping lives in `BUNDLED_CONTEXTS` in `../context.py`.

| Context URL | Final URL after redirects | File | Licence |
| --- | --- | --- | --- |
| `https://w3id.org/ro/crate/1.1/context` | `https://www.researchobject.org/ro-crate/specification/1.1/context.jsonld` | `ro-crate-1.1.json` (version 1.1.3) | CC0 1.0 |
| `https://w3id.org/ro/crate/1.2/context` | `https://www.researchobject.org/ro-crate/specification/1.2/context.jsonld` | `ro-crate-1.2.json` (version 1.2.0) | CC0 1.0 |
| `https://w3id.org/ro/crate/1.2-DRAFT/context` | `https://www.researchobject.org/ro-crate/specification/1.2-DRAFT/context.jsonld` | `ro-crate-1.2.json` (shared) | CC0 1.0 |

## Licence evidence

- **RO-Crate contexts:** each document declares its own licence,
  `"license": {"@id": "https://creativecommons.org/publicdomain/zero/1.0/"}`
  (CC0 1.0), so redistribution is unrestricted. They are published from the
  `ResearchObject/ro-crate` repository.
- **1.2-DRAFT:** the 1.2-DRAFT URL now serves a document identical to the
  published 1.2 context (same SHA-256,
  `27a661f6082735563d9f83145a63876cbe0c0b78624332d3ca05053253eb0d41`, and its
  own `@id` is `https://w3id.org/ro/crate/1.2/context`), so both URLs map to
  `ro-crate-1.2.json`.

## Not bundled

| Context URL | Final URL after redirects | Why not |
| --- | --- | --- |
| `http://purl.archive.org/language-data-commons/context.json` | `https://raw.githubusercontent.com/Language-Research-Technology/language-data-commons-vocabs/master/ontology-context.json` | Hosting repository is GPL-3.0 (`LICENSE` file; `package.json` says `GPL-3.0`) |
| `https://w3id.org/ldac/context` | `https://raw.githubusercontent.com/Language-Research-Technology/ldac-profile/master/context/context.json` | Hosting repository has no `LICENSE` file; its `package.json` says `GPL-3.0-or-later` |

Both Language Data Commons (LDaC) URLs resolved on 2026-10-21 and served the
same document. Neither the document nor the vocabulary crates in those
repositories declare a separate data licence, so the only evidence is
GPL-3.0, and crategraph keeps GPL-licensed material out of its Apache-2.0
distribution. Crates that use these contexts get an "unresolved
context" warning unless the user passes `fetch_contexts=True`. They can be
bundled once the maintainers publish the context under a permissive licence
(such as CC0 or CC BY 4.0).
