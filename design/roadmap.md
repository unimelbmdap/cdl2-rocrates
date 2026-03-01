# Roadmap

Planned features and future directions for crategraph. These are deferred until there's a concrete use case driving the design, rather than building speculatively.

## Plugin Implementations

Extension points that exist as ABCs but have no concrete implementations yet:

- **Writers** — serialisation to JSON-LD, GEXF, Gephi-ready formats (with pre-computed layout and styling)
- **Validators** — RDF/schema.org compliance checking, crate structure validation. Should report issues without blocking usage.
- **Additional readers** — GEXF, CSV, NetworkX graph import

## Interoperability

Export methods to bridge crategraph with other tools:

```python
# Drop down to NetworkX for custom analysis
G = result.to_networkx()

# Export to JSON-LD
result.to_jsonld("output.json")

# Export to Gephi with pre-computed layout
result.to_gephi("output.gexf", layout=True, colour_by="type", size_by="degree")
```

## Natural Language Query Interface

LLM-driven graph querying — ask a question in plain language, get back a result:

```python
result = crate.ask("Which organisations in Melbourne had the most members in the 1880s?")
result.visualise()
```

This is likely simpler to implement over a NetworkX backend (LLM generates Python using the existing `select`/`where`/`pattern` API) than over SPARQL or Cypher. The existing chainable API is already close to natural language in structure, which should make prompt engineering more tractable.

## Third-Party Plugin Registration

Entry points for installable plugins:

```toml
# In a third-party package's pyproject.toml
[project.entry-points."crategraph.readers"]
my_format = "my_package:MyFormatReader"
```

This would let users `pip install crategraph-myformat` and have it automatically available. Not needed until there are actual third-party plugins.
