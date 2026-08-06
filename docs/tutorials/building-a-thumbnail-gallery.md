# Building a thumbnail gallery

RO-Crates often carry more than metadata. A heritage collection may hold scanned documents,
audio, and photographs alongside the records that describe them. This tutorial turns a
collection's images into a small interactive gallery: a grid of thumbnails you can hover to
read what each one is.

We'll use the **Farms to Freeways** oral-history collection, the same dataset as the
[mapping tutorial](mapping-collection-places.md). The collection holds portraits of the women interviewed, scans of
transcripts, and other paperwork.

## What you'll learn

- Finding the entities in a crate that carry an image.
- Selecting a subset of a collection to display.
- Assembling the thumbnails into an interactive gallery with one call to `gallery()`.

## Running this tutorial

Install crategraph and Jupyter, then launch a notebook:

```bash
python -m pip install crategraph jupyter
jupyter notebook
```

## 1. Load the crate

```python
from crategraph import Crate

crate = Crate("data/ldaca/farms-to-freeways")
crate
```

```
Graph(763 entities, 1765 relationships, source='data/ldaca/farms-to-freeways')
```

`gallery()` finds entities with images on its own: any entity that carries a `thumbnail`, or
that is itself an image file. Calling it on the whole crate would mix in the portraits of
identifiable people, so we first narrow to the project's documents.

## 2. Find the documents

`gallery()` would happily include the portraits too, so we narrow to the documents first. The
crate catalogues each item by the physical form it was digitised from; `entity_counts` tallies
any field, so it shows what formats are present:

```python
crate.entity_counts("originalFormat")
```

`entity_counts` returns a `Records` object (a list of `{field, count}` dictionaries) that
previews itself as a table in a notebook:

| originalFormat | count |
| --- | --- |
| audio cassette tape (1) | 50 |
| audio cassette tapes (2) | 18 |
| Paper | 8 |
| Note card | 1 |

Most items are the recorded interviews on audio cassette; nine are paper documents, the
letters, fliers, and a note we want to show. We flag those two formats with `annotate_entities`,
then keep them with `where`:

```python
document_formats = {"Paper", "Note card"}
docs = (
    crate
    .annotate_entities(
        is_document=lambda e: any(f in document_formats for f in e.get("originalFormat") or [])
    )
    .where(is_document=True)
)
docs
```

```
Graph(9 entities, 1 relationships, source='data/ldaca/farms-to-freeways')
```

Deriving a boolean and filtering on it, rather than calling `where(originalFormat="Paper")`
directly, sidesteps a wrinkle: `originalFormat` is stored as a list, and `where` matches values
exactly. `gallery()` then finds each document's scanned image on its own.

## 3. Build the gallery

`gallery()` locates the image for each document (here, each one's `thumbnail`), embeds it as
base64 directly in the page, and lays the thumbnails out in a CSS grid. Every image is
embedded inline, so the result is a single self-contained file with nothing else to manage.

Two optional arguments label the tiles: `caption` puts text under each one, and `hover`
reveals text over the image on mouse-over. Both take a property name. We caption each tile with
its `description` and reveal the full `name` on hover. Nine documents fit a three-column grid:

```python
docs.gallery(caption="description", hover="name", columns=3, filepath="gallery.html")
```

```
'gallery.html'
```

Passing `filepath` writes the page and returns its path; omit it to display the gallery inline
in a notebook instead. By default `gallery()` embeds at most 48 thumbnails (and warns if a
graph holds more), since every image travels inside the page; pass `limit=None` to embed them
all, or narrow the graph further with [`where`](../api/graph.md) as we did above.

## 4. The gallery

The page is self-contained, so it drops straight into a notebook or a docs page. Hover any
tile to read the document's full title.

<iframe src="../../assets/farms-to-freeways-gallery.html" width="100%" height="1120"
        style="border:none" loading="lazy" scrolling="no" title="Farms to Freeways document gallery"></iframe>

## Next steps

The same call works for any images a crate carries: drop the filtering step to gallery a whole
small crate, or swap in a different filter to show another slice. `crate.files` lists every
`File` entity, and `crate.inspect(entity)` reads a file's content (handy for previewing a
document or transcript). Pair this with [Mapping the places in a collection](mapping-collection-places.md)
to put the same collection on a map, or [Visualising a collection](visualising-a-collection.md)
to see its network.
