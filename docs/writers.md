# Writers Guide

The writer subsystem serialises a `Graph` to external formats for use in other tools — Gephi, yEd, pandas, R, Excel, or any tool that reads GraphML or CSV. The single entry point is `graph.write(path, format=...)`. Researchers who want to hand off filtered graph data to a separate analysis environment will use this most often.

Format registration is open: third-party packages can add new formats by subclassing `Writer` and calling `register_writer`. The two built-in formats are GraphML and CSV.

## Formats

| Format key | Output shape | Typical consumer | Notes |
|---|---|---|---|
| `"graphml"` | Single `.graphml` file | Gephi, yEd, NetworkX `read_graphml`, pandas | All attributes serialised as scalars; lxml preferred, pure-Python fallback. Round-tripping preserves string values; numeric types (`int`, `float`, `bool`) survive GraphML's typed attribute system. |
| `"csv"` | Directory with `nodes.csv` + `edges.csv` | pandas `read_csv`, R `read.csv`, Excel | All cells are strings when read back. Pipe-delimited lists and JSON blobs can be decoded with `decode_pipe_list` and `json.loads` respectively. |

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

## Graph.to_networkx()

`graph.to_networkx(copy=True)` returns the underlying `nx.MultiDiGraph` directly, bypassing all writer machinery. This is useful when you need NetworkX algorithms not exposed through the crategraph API.

```python
import networkx as nx

G = crate.to_networkx()          # deep copy — safe to mutate
G_raw = crate.to_networkx(copy=False)  # internal graph — do not mutate
```

With `copy=True` (the default), the returned graph is a fully detached deep copy. You can mutate nodes, edges, and any nested dicts without affecting the source `Graph`. This matters because `@dataclass(frozen=True)` freezes the top-level `Entity` and `Relationship` objects but not their `properties` dicts — a deep copy is the only safe isolation.

With `copy=False`, the internal `MultiDiGraph` is returned directly. Only use this when you need maximum performance and can guarantee you will not mutate the result (e.g. read-only NetworkX algorithms, export pipelines).

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
- Parallel edges with the same source, target, and type are preserved using the edge `key` attribute. Reified relationships use their `rel.id` as the key; others get an auto-assigned integer key.
- Uses `nx.write_graphml_lxml` (requires `lxml`) for performance. Falls back to `nx.write_graphml` (pure Python) if `lxml` is not installed.
- Reading back with NetworkX: `nx.read_graphml("output.graphml")` — note that NetworkX may reassign node IDs on read; use `node_default=True` and check the `id` attribute column.
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

The existing `GraphMLWriter` (`crategraph/writers/graphml.py`) and `CsvWriter` (`crategraph/writers/csv_writer.py`) are the canonical references. Both use `flatten_node` and `flatten_edge` from `crategraph.writers._flatten` to handle the scalar-conversion step — reuse these if your target format also requires scalar-only attributes.
