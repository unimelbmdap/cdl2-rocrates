# crategraph — Agent Orientation

This file helps AI coding agents orient themselves in the crategraph codebase.
Read the linked documents before making changes.

## Key Documentation

| Document | Purpose |
|----------|---------|
| [docs/architecture.md](docs/architecture.md) | High-level design, plugin subsystems, data flow diagram |
| [docs/decisions.md](docs/decisions.md) | Rationale behind backend, data model, and plugin contract choices (internal; excluded from the published site) |
| [docs/getting-started.md](docs/getting-started.md) | Setup, installation, and quick-start examples |
| [docs/api/](docs/api/) | Full API reference (Graph, models, types, interfaces) |

## Conventions

- **Australian English** spelling in all custom names and comments (`analyse`, `colour`, `organisation`). Keep original spelling for external library APIs.
- **Immutable Graph** — every filtering/transformation returns a new `Graph`. No in-place mutation.
- **Plugin architecture** via ABCs defined in `crategraph/core/interfaces.py` (Reader, Writer, Renderer, Validator, Inspector, Viewer).
- **Chainable API** — `crate.select(...).where(...).expand(...)`.
- **Code style** — Ruff formatting and linting enforced via pre-commit hooks (see `.pre-commit-config.yaml`).
- **Search returns Graph or records.** Methods on `Graph` return either a `Graph` (composing with `where`, `expand`, etc.) or a `_records`-shaped iterator of dicts (DataFrame-friendly). Use `Graph.search(query, mode=...)` for subgraph results, `Graph.chunk_records(query=...)` for ranked dict records with scores. For typed `SearchHit` objects (chunk-level provenance with score/text as fields), use `crategraph.index.Searcher` directly.

## Project Layout

```
crategraph/
├── core/           # Graph facade, filtering, transforms, presentation, analysis, models
├── index/          # Text indexing and search (chunker, indexer, Searcher, store)
├── readers/        # Data loaders (ROCrateReader, RdfReader, OKFReader, OHRMCsvReader, OHRMSqlReader, SimpleFolderReader)
│   └── shared/     # Base classes (TabularGraphReader, CsvGraphReader, SqlGraphReader)
├── renderers/      # Visualisation (Pyvis 2D, ForceGraph3D, SVG, Sigma.js, Gallery)
├── inspectors/     # File inspection (MarkItDown)
├── validators/     # Data quality checks (planned)
├── viewers/        # Rich file previews (DefaultViewer)
└── writers/        # Export/serialisation (GraphML, CSV, Text shipped; RDF, RO-Crate planned)
tests/              # Mirrors source layout
docs/               # MkDocs source (Material theme)
```

## Testing

```sh
uv run pytest          # run full test suite
uv run pytest -x       # stop on first failure
```
