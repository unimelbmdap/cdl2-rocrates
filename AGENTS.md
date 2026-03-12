# crategraph — Agent Orientation

This file helps AI coding agents orient themselves in the crategraph codebase.
Read the linked documents before making changes.

## Key Documentation

| Document | Purpose |
|----------|---------|
| [docs/architecture.md](docs/architecture.md) | High-level design, plugin subsystems, data flow diagram |
| [design/api-design.md](design/api-design.md) | Design principles, public API surface, directory layout |
| [design/decisions.md](design/decisions.md) | Rationale behind backend, data model, and plugin contract choices |
| [design/roadmap.md](design/roadmap.md) | Planned features and extensions |
| [docs/getting-started.md](docs/getting-started.md) | Setup, installation, and quick-start examples |
| [docs/api/](docs/api/) | Full API reference (Graph, models, types, interfaces) |

## Conventions

- **Australian English** spelling in all custom names and comments (`analyse`, `colour`, `organisation`). Keep original spelling for external library APIs.
- **Immutable Graph** — every filtering/transformation returns a new `Graph`. No in-place mutation.
- **Plugin architecture** via ABCs defined in `crategraph/core/interfaces.py` (Reader, Writer, Renderer, Validator, Inspector).
- **Chainable API** — `crate.select(...).where(...).expand(...)`.
- **Code style** — Ruff formatting and linting enforced via pre-commit hooks (see `.pre-commit-config.yaml`).

## Project Layout

```
crategraph/
├── core/           # Graph, models, backends, query, interfaces
├── readers/        # Data loaders (ROCrateReader, CsvGraphReader, OHRMCsvReader)
├── renderers/      # Visualisation (Pyvis 2D, ForceGraph3D, SVG)
├── inspectors/     # File inspection (MarkItDown)
├── validators/     # Data quality checks (planned)
├── viewers/        # Viewer subsystem
└── writers/        # Export/serialisation (planned)
tests/              # Mirrors source layout
docs/               # MkDocs source (Material theme)
design/             # Design documents and decision records
```

## Testing

```sh
uv run pytest          # run full test suite
uv run pytest -x       # stop on first failure
```
