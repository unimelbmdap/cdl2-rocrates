# Getting Started

This guide walks you through installing crategraph and using it to explore an RO-Crate collection. No prior experience with Python graph libraries is needed.

## Installation

Install crategraph using pip:

```bash
pip install crategraph
```

If you want to extract text content from files in the crate (PDFs, Word documents, spreadsheets, etc.), install the optional inspection support:

```bash
pip install crategraph[inspect]
```

!!! tip "Using Jupyter notebooks"
    crategraph is designed to work well in [Jupyter notebooks](https://jupyter.org/), where results display as rich HTML. Everything in this guide also works in plain Python scripts.

## Loading a crate

Start by loading an RO-Crate directory. This reads the `ro-crate-metadata.json` file and builds a graph of all the entities and relationships it describes.

```python
from crategraph import Crate

crate = Crate("path/to/my-collection/")
crate
```

```
Graph(142 entities, 387 relationships, source='path/to/my-collection/')
```

To get a quick overview of what's in the crate, use `summary()`:

```python
crate.summary()
```

This shows a breakdown of entity types (people, files, organisations, etc.) and relationship types (author, hasPart, etc.) in the collection.

## Exploring the graph

### Browsing entity types

Every entity in the crate has one or more types. You can see what types are available:

```python
crate.types
```

```
TypeRegistry(['Person', 'File', 'Organisation', 'Dataset', 'Place', ...])
```

### Filtering by type

Use `select()` to narrow down to entities of a particular type. This returns a new graph containing only the matching entities and their connections to each other:

```python
people = crate.select(entity_types=["Person"])
people
```

```
Graph(23 entities, 8 relationships)
```

### Filtering by property values

Use `where()` to filter by exact property values:

```python
crate.where(name="Alice Smith")
```

### Filtering by date

Use `select(time_range=)` to find entities within a year range. This automatically searches common date properties (`startDate`, `endDate`, `datePublished`, etc.) and extracts years from ISO date strings:

```python
crate.select(time_range=(1900, 1950))
```

### Chaining filters

All filtering methods return a new graph, so you can chain them together to progressively refine your results:

```python
crate.select(entity_types=["Person"]).where(name="Alice Smith")
```

## Visualising

### Interactive network visualisation

Generate an interactive network diagram that you can pan, zoom, and click:

```python
crate.visualise()
```

This creates an HTML visualisation where nodes are coloured by type and sized by number of connections. You can save it to a file:

```python
crate.visualise(filepath="my-network.html")
```
You can open this HTML in a new browser:

```python
!open "my-network.html"
```

### Quick overview with glimpse

For a high-level view of the crate's structure, `glimpse()` shows one node per entity type with counts:

```python
crate.glimpse()
```

This is useful for orienting yourself in an unfamiliar collection before drilling into specific entities.

### 3D visualisation

For larger collections, a 3D visualisation can help separate clusters:

```python
crate.visualise(renderer="3d")
```

## Inspecting files

RO-Crates often contain data files — documents, images, spreadsheets, and more. You can check whether an entity references a file using `has_data`:

```python
entity = crate.get("documents/report.pdf")
entity.has_data
```

```
True
```

### Viewing a file

To see a rich preview of a file (images, tables, audio players, etc.):

```python
crate.view("documents/report.pdf")
```

### Extracting text content

To extract the text content from a file (requires `crategraph[inspect]`):

```python
info = crate.inspect("documents/report.pdf")
print(info.content[:500])
```

This converts the file to text using [markitdown](https://github.com/microsoft/markitdown), making it available for further analysis.

## Searching

You can also search for entities by text in their properties using `search()`:

```python
crate.search("Melbourne")
```

This performs fuzzy matching, so it handles minor misspellings. It returns a graph of matching entities and their connections.

## Next steps

- Browse the [Tutorials](tutorials/index.md) for guided walkthroughs using real datasets
- See the [API Reference](api/index.md) for the full list of methods
- Check out the [Resources](resources.md) page for publicly available RO-Crate collections to explore
