# API Reference

crategraph's public API is centred on the [`Graph`](graph.md) class. The [`Crate`](graph.md#crategraph.Crate) convenience subclass loads RO-Crate data, but all filtering, transformation, and visualisation methods live on `Graph`.

- [**Graph & Crate**](graph.md) — loading, filtering, transforming, and visualising graphs
- [**Data Models**](models.md) — `Entity`, `Relationship`, `FileInfo`, and validation models
- [**Type Discovery**](types.md) — `TypeRegistry` for fuzzy type validation and autocomplete
- [**Plugin Interfaces**](interfaces.md) — ABCs for extending crategraph with custom readers, writers, renderers, validators, and inspectors
