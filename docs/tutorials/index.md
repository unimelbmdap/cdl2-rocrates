# Tutorials

Step-by-step guides for working with RO-Crate collections using crategraph. Each tutorial uses a real, publicly available dataset so you can follow along.

If you haven't already, start with the [Getting Started](../getting-started.md) guide for installation and basic usage.

## Available tutorials

- [From graph to DataFrame](from-graph-to-dataframe.md) — Annotate entities with derived fields, filter on them, then flatten to pandas and write a CSV
- [Exploring temporal dimensions of RO-Crates](exploring-temporal-dimensions.md) — Parse messy dates, recover years from titles, and draw a timeline of a crate's events
- [Mapping the places in a collection](mapping-collection-places.md) — Follow geometry links, read coordinates from WKT, and draw an interactive map of one or several crates
- [Visualising a collection](visualising-a-collection.md) — Glimpse a crate's types, render the whole network, and explore subsets interactively and in 3D
- [Building a thumbnail gallery](building-a-thumbnail-gallery.md) — Find a crate's images, select a subset, and assemble an interactive thumbnail gallery with `gallery()`
- [Searching a collection](searching-a-collection.md) — Fuzzy-match a collection's metadata, then build a semantic index and search the text by meaning
- [Basic NLP with text records](basic-nlp-with-text-records.ipynb) — Use graph filtering and metadata grouping before handing text to NLP tools
- [Cheat sheet](crategraph-cheatsheet.md) — Condensed reference for the main crategraph operations

## Data sources

These tutorials use openly available datasets, most discoverable through the
[LDaCA data portal](https://data.ldaca.edu.au/search). Licences below are as declared in each
dataset's RO-Crate metadata; please attribute the original collections if you reuse the data.

- **Farms to Freeways Example Dataset** (mapping and gallery tutorials). Licence: [CC BY 3.0 AU](https://creativecommons.org/licenses/by/3.0/au/). Source: [From Farms to Freeways project](https://omeka.uws.edu.au/farmstofreeways/).
- **A Corpus of Oz Early English (COOEE)** (mapping tutorial). Licence: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Source: [Monash Bridges](https://bridges.monash.edu/articles/dataset/Corpus_of_Oz_Early_English_COOEE_/23961609).
- **Australian Corpus of English** (NLP tutorial). Licence: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Source: [doi:10.25949/24629712](https://doi.org/10.25949/24629712).
- **Australian Radio Talkback** (search tutorial). Licence: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Source: [LDaCA, doi:10.25949/24769434](https://doi.org/10.25949/24769434).
- **Australian Slang Survey Data** (mapping tutorial). Licence: [CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/) (non-commercial, no derivatives). Source: [Monash Bridges](https://bridges.monash.edu/articles/dataset/Australian_Slang_Survey_Data/30102115).
- **University of Melbourne Perpetual Calendar (UMPC)** (temporal and mapping tutorials, and the cheat sheet). Licence: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Source: [UMPC website](https://umpc.esrc.unimelb.edu.au/index.html).
- **Encyclopedia of Australian Science and Innovation (EOAS)** (visualisation tutorial). Licence: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Source: [eoas.info](https://www.eoas.info/).
