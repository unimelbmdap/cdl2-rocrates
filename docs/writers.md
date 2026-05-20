# Writers Guide

The writer subsystem serialises a `Graph` to external formats for use in other tools — Gephi, yEd, pandas, R, Excel, text-analysis packages, or any tool that reads GraphML, CSV, or plain text. The single entry point is `graph.write(path, format=...)`. Researchers who want to hand off filtered graph data or graph-associated material to a separate analysis environment will use this most often.

Format registration is open: third-party packages can add new formats by subclassing `Writer` and calling `register_writer`. The built-in formats are GraphML, CSV, and plain text.

## Tabular export

Two paths to a tabular view of a graph:

| Output | Method | When to use |
| --- | --- | --- |
| In-memory `list[dict]` | `graph.entity_records()` / `graph.relationship_records()` | Notebook analysis, wrapping with pandas / polars / pyarrow, immediate exploration. No third-party dependencies. |
| On-disk `nodes.csv` / `edges.csv` | `graph.write(path, format="csv")` (see [CSV](#csv) below) | Hand-off to other tools (R, Excel, Gephi), archival, sharing. All values become strings on disk. |

The records methods preserve native Python types (lists stay lists, dicts stay dicts, `None` stays `None`); the CSV writer flattens to scalars because CSV cells require it. Pick whichever matches your downstream workflow.

### In-memory records

```python
from crategraph import Crate

crate = Crate("path/to/crate/")

entity_rows = crate.entity_records()
relationship_rows = crate.relationship_records()

# Wrap with whichever DataFrame library you prefer:
import pandas as pd
nodes_df = pd.DataFrame(entity_rows)
edges_df = pd.DataFrame(relationship_rows)
```

`entity_records()` returns one dict per entity with promoted keys `id`, `label`, `type`, `types` first, then non-colliding property keys sorted alphabetically, then any properties whose names collide with a promoted key emitted as `prop_<key>` (e.g. an entity with a property named `"id"` becomes `prop_id` so the entity's own id stays untouched). `relationship_records()` returns one dict per relationship with promoted keys `source`, `target`, `type`, `rel_id` first under the same ordering rule. `rel_id` is `None` for inline (non-reified) relationships and a string for reified ones — the CSV writer uses an empty string in the same position, so this is the one place the two paths differ. Property values are deep-copied — mutating a returned record does not affect graph state.

## Text export

Two paths to a text view of graph-associated content:

| Output | Method | When to use |
| --- | --- | --- |
| In-memory text records | `graph.text_records()` | Notebook analysis, NLP pipelines, preserving document boundaries and provenance. |
| On-disk corpus file | `graph.write(path, format="text")` (see [Text](#text) below) | Hand-off to text-analysis tools, archival, sharing, or any workflow that expects a plain text file. |

The text writer is a thin export layer over `text_records()`. It does not perform separate extraction logic: file text, property text, filtering, cached index reads, and view restriction all flow through the public text-records API.

`graph.text_records()` defaults to `source_kind="file"`. Pass
`source_kind="properties"` to work with metadata-derived text records, or
`source_kind="all"` to include both file and property text.

For notebook and NLP workflows that need lightweight metadata alongside
the extracted text, pass `include_properties`:

```python
records = list(
    graph.text_records(include_properties=["name", "encodingFormat"])
)
```

Requested properties are added as top-level keys in each record when
present. Pass `include_properties=True` to include all *public* entity
properties (internal `_`-prefixed loader flags such as `_is_root` are
excluded; an explicit allowlist is honoured verbatim). The default is
`False`, so the base record shape remains compact.

## Formats

| Format key | Output shape | Typical consumer | Notes |
|---|---|---|---|
| `"graphml"` | Single `.graphml` file | Gephi, yEd, NetworkX `read_graphml`, pandas | All attributes serialised as scalars; lxml preferred, pure-Python fallback. Round-tripping preserves string values; numeric types (`int`, `float`, `bool`) survive GraphML's typed attribute system. |
| `"csv"` | Directory with `nodes.csv` + `edges.csv` | pandas `read_csv`, R `read.csv`, Excel | All cells are strings when read back. Pipe-delimited lists and JSON blobs can be decoded with `decode_pipe_list` and `json.loads` respectively. |
| `"text"` / `"txt"` | Single `.txt` or `.md` file | Voyant, AntConc, quanteda, NLP notebooks, plain text readers | Writes text records with optional provenance headers. Defaults to file-derived text; can also export property text. |

## Usage

### GraphML

```python
from crategraph import Crate

crate = Crate("path/to/ro-crate")

# Write to a GraphML file
crate.write("output.graphml", format="graphml")

# Overwrite an existing file
crate.write("output.graphml", format="graphml", overwrite=True)
```

The path must end with `.graphml` (or otherwise be a file path — GraphML writes a single file, not a directory).

On a graph with no entities the output is still valid GraphML with an empty graph element.

### CSV

```python
# Write nodes.csv and edges.csv into a new directory
crate.write("output_tables/", format="csv")

# Overwrite contents of an existing non-empty directory
crate.write("output_tables/", format="csv", overwrite=True)
```

The directory is created (including parent directories) if it does not exist. If it already exists and is non-empty, `FileExistsError` is raised unless `overwrite=True`. If the path exists as a non-directory file, `FileExistsError` is raised unconditionally.

Reading the output back with pandas:

```python
import pandas as pd

nodes = pd.read_csv("output_tables/nodes.csv")
edges = pd.read_csv("output_tables/edges.csv")
```

CSV is export-only — there is no CSV reader that reconstructs a `Graph`. Use GraphML (via `nx.read_graphml`) if you need a round-trippable format, or reload the data into pandas/R for downstream analysis.

### Text

```python
# Write extracted file text to one corpus file
crate.write("corpus.txt", format="text")

# Include text built from selected metadata properties instead
crate.write("metadata-text.md", format="text", source_kind="properties")

# Export both file text and property text
crate.write("all-text.txt", format="text", source_kind="all")

# Use cached text from a previously-built semantic index
crate.write("corpus.txt", format="text", store_path="index.db", overwrite=True)
```

Text export writes one UTF-8 file. By default it exports `source_kind="file"`, meaning file contents extracted by `graph.text_records()`. Pass `source_kind="properties"` for metadata-derived text records, or `source_kind="all"` to export both.

Each text unit is separated by a plain `---` delimiter and, by default, begins with provenance headers:

```text
# source_id: minimal-crate
# entity_id: sample.txt
# source_kind: file
# entity_types: File

Extracted text...
```

The writer accepts the same filtering concepts as `text_records()`:

```python
crate.write(
    "selected-corpus.txt",
    format="text",
    filters={"entity_id": ["sample.txt", "notes.md"]},
)
```

When using the writer-level `source_kind` option, do not also include `source_kind` inside `filters`; pass `source_kind="all"` if you want full control through `filters`.

## Listing registered formats

```python
from crategraph.writers import list_formats

list_formats()  # ['csv', 'graphml', 'text', 'txt']
```

Third-party packages that register additional formats show up here automatically once imported.

## Graph.to_networkx()

`graph.to_networkx(copy=True)` returns the underlying `nx.MultiDiGraph` directly, bypassing all writer machinery. This is useful when you need NetworkX algorithms not exposed through the crategraph API.

```python
import networkx as nx

G = crate.to_networkx()          # deep copy — safe to mutate
G_raw = crate.to_networkx(copy=False)  # original Entity/Relationship objects — do not mutate
```

With `copy=True` (the default), the returned graph is a fully detached deep copy. You can mutate nodes, edges, and any nested dicts without affecting the source `Graph`. This matters because `@dataclass(frozen=True)` freezes the top-level `Entity` and `Relationship` objects but not their `properties` dicts — a deep copy is the only safe isolation.

With `copy=False`, the returned `MultiDiGraph` is still rebuilt, but the original `Entity` and `Relationship` objects are attached directly. Only use this when you need lower copy overhead and can guarantee you will not mutate those objects or their nested properties.

## Attribute Flattening Rules

GraphML and CSV both require scalar attribute values (`str`, `int`, `float`, `bool`). The shared flattening module (`crategraph.writers._flatten`) converts rich `Entity` and `Relationship` objects to flat dicts before writing.

### Promoted columns

Every node row begins with these columns in this order:

| Column | Source |
|---|---|
| `id` | `entity.id` |
| `label` | `properties["name"]` → `properties["title"]` → `entity.id` (truthy check — empty strings fall through) |
| `type` | First entry of `entity.types`, or `""` |
| `types` | All types, pipe-delimited (see below) |

Every edge row begins with:

| Column | Source |
|---|---|
| `source` | `rel.source` |
| `target` | `rel.target` |
| `type` | `rel.type` |
| `rel_id` | `rel.id` if set, else `""` |

Remaining property keys are appended in alphabetical order after the promoted columns.

### Property name collisions

If a property key in `entity.properties` or `rel.properties` collides with a promoted column name (e.g. an entity with a `"type"` property), it is emitted as `prop_<key>` (e.g. `prop_type`). This avoids silently overwriting the promoted value.

If a user-defined property is already called `prop_<promoted>` (e.g. both `"id"` and `"prop_id"` appear in `properties`), the user-defined key keeps its name and the promoted-collision value is pushed one level further out. In that example:

- `id` promoted column → `entity.id`.
- User's `prop_id` property → stays at `prop_id`.
- User's `id` property (the promoted-name collision) → `prop_prop_id`.

The prefix chain lengthens as needed so no property is ever dropped.

### Scalar passthrough

| Input type | Output |
|---|---|
| `None` | `""` (empty string) |
| `bool` | `bool` (passed through; checked before `int` because `bool` is a subclass) |
| `int`, `float`, `str` | passed through unchanged |

### Lists of scalars — pipe-delimited encoding

Lists (or tuples) containing only scalar values (`str`, `int`, `float`, `bool`, `None`) are encoded as pipe-delimited strings:

- Backslashes are escaped first: `\` → `\\`
- Then pipes are escaped: `|` → `\|`
- Items are joined with `|`

Example: `["a", "b|c", "d\\e"]` → `"a|b\|c|d\\\\e"`

This encoding is reversible. Import `decode_pipe_list` from `crategraph.writers._flatten` to decode:

```python
from crategraph.writers._flatten import decode_pipe_list

types_str = nodes_df["types"].iloc[0]     # e.g. "Person|Agent"
types_list = decode_pipe_list(types_str)   # ["Person", "Agent"]
```

An empty string decodes to `[]`. The decoder returns strings — original numeric types are not preserved.

### Nested dicts and lists of dicts

Any value that is a `dict`, or a list/tuple containing at least one non-scalar element, is serialised with `json.dumps(value, sort_keys=True, ensure_ascii=False)`. Use `json.loads` to decode:

```python
import json

raw = nodes_df["some_nested_prop"].iloc[0]
decoded = json.loads(raw)
```

## Format-Specific Notes

### GraphML

- Writes a single `.graphml` file (XML-based).
- Parallel edges with the same source, target, and type are preserved using globally unique edge IDs (`e0`, `e1`, ...). Reified relationship IDs are preserved in the `rel_id` attribute.
- Uses `nx.write_graphml_lxml` (requires `lxml`) for performance. Falls back to `nx.write_graphml` (pure Python) if `lxml` is not installed.
- Reading back with NetworkX: `nx.read_graphml("output.graphml")`. Entity IDs round-trip as the NetworkX node keys, and they also appear on each node under the promoted `id` attribute. GraphML attribute values come back typed when `lxml` is available, as strings otherwise — pass `node_type=str` if you want to force string keys regardless.
- Reading back with pandas: `nx.to_pandas_edgelist(nx.read_graphml("output.graphml"))`.

### CSV

- Writes `nodes.csv` and `edges.csv` using Python's stdlib `csv.DictWriter`.
- Column order: promoted columns first (in the fixed order above), then remaining property keys alphabetically.
- Line endings: stdlib `csv` default (`\r\n`) for maximum interoperability with Excel and RFC 4180.
- All values are strings when read back — numeric columns in the original graph are not typed in CSV. Cast explicitly in pandas: `nodes["degree"] = nodes["degree"].astype(int)`.
- An empty graph still produces valid CSV files with header rows.

## Extending — Custom Writers

To add a new export format:

1. Subclass `Writer` from `crategraph.core.interfaces` and implement `can_write(path) -> bool` and `write(graph, path, **kwargs) -> None`.
2. Call `register_writer("myformat", MyWriter)` at import time (e.g. at the bottom of your module).
3. Users can then call `graph.write("output.xyz", format="myformat")`.

The existing `GraphMLWriter` (`crategraph/writers/graphml.py`), `CsvWriter` (`crategraph/writers/csv_writer.py`), and `TextWriter` (`crategraph/writers/text_writer.py`) are the canonical references. GraphML and CSV use `flatten_node` and `flatten_edge` from `crategraph.writers._flatten` to handle the scalar-conversion step — reuse these if your target format also requires scalar-only attributes. Text export instead uses the public `graph.text_records()` API, which is the better pattern for writers over graph-associated content rather than the graph structure itself.
