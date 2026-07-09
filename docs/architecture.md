# Architecture Overview

This page describes how crategraph is structured, to help contributors orient themselves and find the right place to work.

## High-Level Design

crategraph is a **plugin-oriented graph library** for exploring RO-Crate metadata. The central object is `Graph` (with its convenience subclass `Crate`), which holds entities and relationships in memory and stores them in a NetworkX graph. Everything else — reading data in, rendering it out, inspecting files, validating quality — is handled by **plugin subsystems** defined as abstract base classes.

```
                        ┌──────────────────────┐
                        │       Readers        │
                        │  (RO-Crate, folder,  │
                        │    OHRM, RDF)        │
                        └──────────┬───────────┘
                                   │ populate
                                   ▼
                  ┌────────────────────────────┐     ┌─────────────┐
                  │      Graph  /  Crate       │────►│  Renderers  │
                  │                            │     │ (2D/3D/SVG) │
                  │  entities · relationships  │     └─────────────┘
                  │  select · where · pattern  │
                  │  expand · search · query   │     ┌─────────────┐
                  │  merge · collapse · detect │────►│ Inspectors  │
                  │  visualise · glimpse       │     │ (MarkItDown)│
                  │  view · inspect            │     └─────────────┘
                  └────────────┬───────────────┘
                               │                     ┌─────────────┐
                               ├────────────────────►│   Viewers   │
                               │                     │ (Default)   │
                               │                     └─────────────┘
                               ▼
                  ┌────────────────────────────┐
                  │       Validators           │
                  │        (planned)           │
                  └────────────────────────────┘
                  ┌────────────────────────────┐
                  │   Writers (GraphML, CSV)   │
                  │  (RDF, RO-Crate planned)   │
                  └────────────────────────────┘
```

**Key principle:** every filtering or transformation method returns a **new** `Graph` — nothing is mutated in place. This makes operations chainable (`crate.select(...).where(...).expand(...)`) and branching natural.

## Package Layout

```
crategraph/
├── __init__.py            # Public entry point: Crate class + re-exports
├── core/                  # The heart of the library
│   ├── graph.py           # Graph class — public facade, state, and plumbing
│   ├── filtering.py       # select(), where(), search(), expand(), pattern(), query()
│   ├── transforms.py      # merge_nodes(), simplify(), collapse_edges()
│   ├── presentation.py    # layout(), visualise(), glimpse(), inspect(), view()
│   ├── analysis.py        # summary(), most_connected(), profile(), detect_communities()
│   ├── models.py          # Entity, Relationship, FileInfo, ViewInfo (dataclasses + Pydantic)
│   ├── types.py           # TypeRegistry — fuzzy type discovery
│   ├── corpus.py          # Corpus — batch profiling across multiple crates
│   ├── query.py           # Cypher query support (via grand-cypher)
│   ├── _files.py          # Entity file path resolution helpers
│   ├── _html.py           # Shared _repr_html_ helpers for Jupyter
│   ├── interfaces.py      # ABCs: Reader, Writer, Renderer, Validator, Inspector, Viewer
├── readers/               # Data loaders
│   ├── rocrate.py         # ROCrateReader — parses ro-crate-metadata.json
│   ├── folder.py          # SimpleFolderReader — plain directory → Graph
│   ├── okf.py             # OKFReader — Markdown knowledge bundles
│   ├── rdf.py             # RdfReader — Turtle, RDF/XML, JSON-LD via rdflib
│   ├── ohrm_csv.py        # OHRMCsvReader — OHRM CSV database exports
│   ├── ohrm_sql.py        # OHRMSqlReader — OHRM SQLite databases
│   └── shared/            # Base classes for tabular readers
│       ├── tabular.py     # TabularGraphReader ABC
│       ├── csv_loader.py  # CsvGraphReader (pandas-backed)
│       ├── sql_loader.py  # SqlGraphReader (sqlite3-backed)
│       └── ohrm_tables.py # OHRM schema definitions
├── renderers/             # Visualisation outputs
│   ├── _colours.py        # Shared colour palette and colour-map resolution
│   ├── _validation.py     # Shared CSS-dimension validation for renderer params
│   ├── pyvis.py           # PyvisRenderer — interactive 2D (vis.js)
│   ├── svg.py             # SvgRenderer — static SVG with force layout
│   ├── forcegraph3d.py    # ForceGraph3DRenderer — interactive 3D (Three.js)
│   ├── sigma.py           # SigmaRenderer — WebGL via sigma.js + ForceAtlas2
│   └── templates/         # HTML templates for browser-based renderers
├── inspectors/            # File content inspection
│   ├── __init__.py        # Inspector registry and find_inspector()
│   └── markitdown.py      # MarkItDownInspector — converts files to markdown
├── viewers/               # Rich file previews
│   ├── __init__.py        # Viewer registry and find_viewer()
│   └── default.py         # DefaultViewer — images, CSV tables, audio, etc.
├── validators/            # Data quality checks (planned, ABC only)
└── writers/               # Export/serialisation (GraphML, CSV, text shipped; RDF planned)
```

## Subsystems

Each subsystem is defined by an abstract base class in `crategraph/core/interfaces.py`. To contribute to a subsystem, you implement the relevant ABC and register it.

### Readers

**ABC:** `Reader` — `can_read(path)` and `read(path) -> Graph`

Readers parse external data sources and populate a `Graph` with entities and relationships.

**Current implementations:**

- `ROCrateReader` (`readers/rocrate.py`) — parses `ro-crate-metadata.json` directly as JSON (not via RDFLib). Uses a two-pass approach: first creates entity nodes, then extracts relationship edges. Supports configurable inline relation extraction.
- `SimpleFolderReader` (`readers/folder.py`) — turns a plain directory into a `Graph` (root `Dataset` + nested `Dataset`/`File` entities with `hasPart` edges). Deliberately structural-only; defers to `ROCrateReader` when `ro-crate-metadata.json` is present so users can add it to a `Corpus` alongside the RO-Crate reader without conflicts.
- `OKFReader` (`readers/okf.py`) — loads Open Knowledge Format Markdown bundles. Frontmatter types become entity types, document bodies remain searchable in the `text` property, and internal Markdown links become directed `linksTo` relationships. Requires `crategraph[okf]` (PyYAML and markdown-it-py).
- `RdfReader` (`readers/rdf.py`) — loads any serialisation rdflib recognises (Turtle, RDF/XML, JSON-LD, N-Triples). Preserves full URIs, namespaces, and literal metadata for round-trip fidelity. Requires `crategraph[rdf]` (rdflib).
- `OHRMCsvReader` (`readers/ohrm_csv.py`) — reads OHRM CSV database exports using the shared tabular reader infrastructure. Requires `crategraph[ohrm]` (pandas).
- `OHRMSqlReader` (`readers/ohrm_sql.py`) — reads OHRM SQLite databases via the shared SQL loader. Requires `crategraph[ohrm]`.
- `TabularGraphReader` (`readers/shared/tabular.py`) — abstract base for table-driven readers, with `CsvGraphReader` and `SqlGraphReader` as concrete loaders.

**Contribution ideas:** readers for other formats (GEXF, GraphML, RiC-O via RDFLib).

### Renderers

**ABC:** `Renderer` — `render(graph, **kwargs) -> Any`

Renderers take a `Graph` and produce a visual output. Common parameters include `colour_by`, `size_by`, `filepath`, and `height`/`width`.

**Current implementations:**

- `SigmaRenderer` (`renderers/sigma.py`) — default (`"2d"`). WebGL-accelerated rendering via sigma.js with ForceAtlas2 client-side layout. Handles large graphs efficiently. No extra Python dependencies.
- `SvgRenderer` (`renderers/svg.py`) — static SVG with a custom Fruchterman–Reingold force layout. Includes post-layout overlap removal. Also used by `glimpse()`.
- `ForceGraph3DRenderer` (`renderers/forcegraph3d.py`) — 3D interactive via a bundled HTML template using the 3d-force-graph (Three.js) library.
- `PyvisRenderer` (`renderers/pyvis.py`) — interactive 2D HTML network using pyvis/vis.js. Requires `pip install crategraph[pyvis]`.

All renderers share colour assignment via `_colours.py:resolve_colour_map()`, which supports colouring by any entity attribute and automatic community detection.

**Contribution ideas:** Matplotlib/static image renderer, Graphviz/DOT export, Gephi-compatible output.

### Inspectors

**ABC:** `Inspector` — `supports(path) -> bool` and `inspect(path) -> FileInfo`

Inspectors examine data files referenced by entities and return structured information about them.

**Current implementations:**

- `MarkItDownInspector` (`inspectors/markitdown.py`) — wraps the `markitdown` package to convert files to markdown. Supports any file format that MarkItDown handles internally.

The inspector registry (`inspectors/__init__.py`) maintains an ordered list of inspector classes. `find_inspector(path)` returns the first inspector whose `supports()` method matches the resolved file path.

**Contribution ideas:** specialised inspectors for tabular data (CSV/Excel previews), image metadata (EXIF), audio/video metadata, or geospatial files.

### Viewers

**ABC:** `Viewer` — `supports(path) -> bool` and `view(path) -> ViewInfo`

Viewers produce rich HTML previews of data files referenced by entities — images displayed inline, CSVs as HTML tables, audio with playback controls.

**Current implementations:**

- `DefaultViewer` (`viewers/default.py`) — handles images, CSV/TSV tables, audio, video, text, and HTML files with format-specific rendering.

The viewer registry (`viewers/__init__.py`) works like the inspector registry: `find_viewer(path)` returns the first viewer whose `supports()` method matches the resolved file path.

### Validators

**ABC:** `Validator` — `validate(graph) -> ValidationReport`

Validators check a graph for data quality issues and return a report of problems found.

**Current status:** the ABC and data models (`ValidationReport`, `ValidationIssue`) exist, but there are no concrete implementations yet.

**Contribution ideas:** schema.org conformance checking, RO-Crate profile validation, broken-link detection, completeness checks (e.g. entities missing required properties).

### Writers

**ABC:** `Writer` — `can_write(path) -> bool` and `write(graph, path, **kwargs) -> None`

Writers serialise a `Graph` or graph-associated material to an external format. The writer registry (`writers/__init__.py`) maps format names to writer classes via `register_writer(name, cls)` and `get_writer(name)`. Requesting an unknown format raises `UnknownFormatError` (a `ValueError` subclass).

The public entry point is `graph.write(path, *, format, overwrite=False, **kwargs)` on the `Graph` class, which dispatches to the registered writer for `format`.

**Current implementations:**

- `GraphMLWriter` (`writers/graphml.py`) — writes a single `.graphml` file. Compatible with Gephi, yEd, and NetworkX's `read_graphml`. Uses `nx.write_graphml_lxml` with a pure-Python fallback.
- `CsvWriter` (`writers/csv_writer.py`) — writes `nodes.csv` and `edges.csv` into a target directory. A non-empty directory without `overwrite=True` raises `FileExistsError`.
- `TextWriter` (`writers/text_writer.py`) — writes graph-associated text records to a single UTF-8 `.txt` or `.md` file for corpus and NLP handoff.

GraphML and CSV rely on the shared flattening module (`writers/_flatten.py`) to convert nested `Entity`/`Relationship` properties to scalar-only attributes. Text export uses the public `Graph.text_records()` API. See [docs/writers.md](writers.md) for writer-specific details.

**Contribution ideas:** JSON-LD / RDF export, GEXF export, RO-Crate round-trip export, Neo4j import format.

### Analysis and Query

These modules live in `core/` and extend `Graph` with analytical capabilities:

- `analysis.py` — `summary()` (entity/relationship counts with bar chart), `most_connected()` (degree ranking), `profile()` (structural metrics: density, components, degree stats), `detect_communities()` (Louvain algorithm), `merge_by_primary_type()` (used by `glimpse()`).
- `corpus.py` — `Corpus` class for batch profiling across multiple crates. Accepts glob patterns, profiles each crate independently, returns `CorpusProfile` with optional DataFrame export.
- `query.py` — Cypher query support via `grand-cypher`. Supports shorthand patterns that auto-expand to full `MATCH ... RETURN` queries.

## Data Flow

A typical workflow moves data through the system like this:

1. **Load:** a `Reader` parses a source (e.g. an RO-Crate directory) into `Entity` and `Relationship` objects, stored in a `Graph`.
2. **Explore:** the user filters and transforms the graph using chainable methods (`select`, `where`, `pattern`, `expand`, `search`, `query`). Each returns a new `Graph`.
3. **Visualise:** a `Renderer` takes the current graph and produces output (HTML, SVG, or in-memory object).
4. **View:** a `Viewer` produces a rich HTML preview of a file (images, tables, audio players).
5. **Inspect:** an `Inspector` examines a file referenced by an entity and returns a `FileInfo` with content and metadata.
6. **Validate** *(planned)*: a `Validator` checks the graph against quality rules and returns a `ValidationReport`.
7. **Export**: a `Writer` serialises the graph to a file. `graph.write(path, format="graphml")` and `graph.write(path, format="csv")` are available; RDF export is planned.

## Where to Start

| I want to...                        | Look at...                                                |
|-------------------------------------|-----------------------------------------------------------|
| Add a new data format               | `core/interfaces.py:Reader`, then `readers/rocrate.py` as a reference |
| Build a new visualisation           | `core/interfaces.py:Renderer`, then any file in `renderers/` |
| Add a file inspector                | `core/interfaces.py:Inspector`, then `inspectors/markitdown.py` |
| Add a file viewer                   | `core/interfaces.py:Viewer`, then `viewers/default.py`    |
| Implement validation                | `core/interfaces.py:Validator` and `core/models.py:ValidationReport` |
| Add an export format                | `core/interfaces.py:Writer`, then `writers/graphml.py` as a reference |
| Add analytical features             | `core/analysis.py`                                        |
| Add filtering or query methods      | `core/filtering.py`                                       |
| Add graph transforms                | `core/transforms.py`                                      |
| Add visualisation or file access    | `core/presentation.py`                                    |
| Work on Cypher query support        | `core/query.py`                                           |
