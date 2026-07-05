# Combining multiple crates

Sometimes you may want to ask questions across more than one RO-Crate. Separate collections may share a
language, a researcher, an institution, a place, or a period of activity. Before joining
them, decide which kind of overlap matters for your question. This tutorial loads three
crates at once, joins them through a shared language, then uses a map to show another
possible connection.

We'll use three **PARADISEC** collections related to South Efate, Vanuatu:
[NT1](https://catalog.paradisec.org.au/collection?id=https%3A%2F%2Fcatalog.paradisec.org.au%2Frepository%2FNT1)
and
[NT8](https://catalog.paradisec.org.au/collection?id=https%3A%2F%2Fcatalog.paradisec.org.au%2Frepository%2FNT8),
both deposited by Nick Thieberger, and
[BR1](https://catalog.paradisec.org.au/collection?id=https%3A%2F%2Fcatalog.paradisec.org.au%2Frepository%2FBR1),
deposited by Rosey Billington. They were created independently but overlap by design.

These are **metadata-only** crates: the records describe the recordings, but the audio
sits behind PARADISEC's access conditions. Metadata is all we need to find the overlaps.

## What you'll learn

- Loading several crates into one graph with `Crate(...)`.
- Why the crates arrive as disconnected islands, and how to see it.
- Reading a type-coloured network before switching to collection colours.
- Choosing what counts as the "same thing" across collections.
- Using a shared identifier to bring matching records together.
- Using `merge_nodes` to reveal what the crates share and watch the separate collections join into one connected graph.
- Drawing dataset-coloured place footprints to spot a different kind of join you have not made yet.

## Running this tutorial

This tutorial uses Jupyter, Plotly, and Shapely alongside `crategraph`:

```bash
uv run --all-extras --with jupyter,plotly,shapely jupyter notebook
```

## 1. Load several crates at once

`Crate` takes more than one path. Each crate is read in turn, and crategraph adds the
crate's directory name to each id so two crates can never collide:

```python
from crategraph import Crate

combined = Crate(
    "docs/tutorials/data/paradisec/NT1",
    "docs/tutorials/data/paradisec/NT8",
    "docs/tutorials/data/paradisec/BR1",
    include_root=True,
)
combined
```

```
Graph(61 entities, 65 relationships, sources=['BR1', 'NT1', 'NT8'])
```

`include_root=True` keeps each collection's root entity in the graph, because that is
what links a collection to its languages, people, and places. Every node now carries a
prefixed id like `NT1/...`; the original id is preserved on each node as `raw_id`,
which we rely on shortly. Because loading does not invent links between separate crates,
the three collections arrive as **three disconnected islands**.

Before looking for overlaps, look at the graph using crategraph's normal type colours.
The legend shows what kind of thing each node is: collection roots, files, languages,
people, places, organisations, and so on. These colours do **not** show which crate a
node came from yet.

```python
combined.visualise(colour_by="type", simple=False, filepath="paradisec-type-network.html")
```

<iframe src="../../assets/paradisec-type-network.html" width="100%" height="520"
        style="border:none" loading="lazy" scrolling="no" title="Three PARADISEC crates coloured by entity type"></iframe>

This view is useful for orientation. It shows that languages are part of the same
metadata structure as people, places, and collection records. For the merge question,
though, we need to see which crate each node came from.

## 2. See the duplication

First tag every node with the crate it came from (the prefix on its id), using
`annotate_entities` to derive a new `origin` field. Then look at the languages: rather
than reaching into each entity by hand, ask for them as records and sort the table so the
duplication is easy to see.

```python
tagged = combined.annotate_entities(origin=lambda e: e.id.split("/")[0])
langs = tagged.select(entity_types=["Language"]).entity_records(columns=["name", "origin", "raw_id"])
sorted(langs, key=lambda r: (r["name"], r["origin"]))
```

```
[{'name': 'Bislama', 'origin': 'BR1', 'raw_id': 'http://www.language-archives.org/language/bis'},
 {'name': 'Bislama', 'origin': 'NT1', 'raw_id': 'http://www.language-archives.org/language/bis'},
 {'name': 'Efate, South', 'origin': 'BR1', 'raw_id': 'http://www.language-archives.org/language/erk'},
 {'name': 'Efate, South', 'origin': 'NT1', 'raw_id': 'http://www.language-archives.org/language/erk'},
 {'name': 'Efate, South', 'origin': 'NT8', 'raw_id': 'http://www.language-archives.org/language/erk'},
 {'name': 'English', 'origin': 'BR1', 'raw_id': 'http://www.language-archives.org/language/eng'},
 {'name': 'Lelepa', 'origin': 'NT1', 'raw_id': 'http://www.language-archives.org/language/lpa'}]
```

**Efate, South** appears three times, once each from BR1, NT1, and NT8, and every one of
them carries the *identical* `raw_id`, an [OLAC](http://www.language-archives.org/)
language URI. So the crates already agree on an identifier for the language; the three
nodes are only separate because loading namespaced their ids.

That does not mean language is the only valid way to connect these crates. It is the
right key for the question we are asking here: "which collections document the same
language?" If the question were about depositors, institutions, places, or recording
periods, we would make a different choice and get a different joined graph.

You can see the same split in the network. Colour the graph by `origin` (`simple=True`
drops the side panel, whose legend is keyed to entity types rather than our `origin`
field):

```python
tagged.visualise(colour_by="origin", simple=True, filepath="paradisec-origin-network.html")
```

<iframe src="../../assets/paradisec-origin-network.html" width="100%" height="480"
        style="border:none" loading="lazy" scrolling="no" title="Three PARADISEC crates coloured by origin"></iframe>

Three clusters, three colours, no lines between them. Each collection hangs off its own
root, and the shared South Efate language is duplicated once per crate. Joining them
for this question means making those duplicate language nodes into one node.

## 3. Choose what should match

Now make that choice explicit in the data. For language nodes, use the shared `raw_id`.
For everything else, keep the prefixed id so those records stay separate. That means
only languages can be joined in this example:

```python
def share_key(e):
    """Shared id for languages; every other node stays distinct."""
    return e.get("raw_id") if "Language" in e.types else e.id

keyed = tagged.annotate_entities(share_key=share_key)
```

## 4. Merge, and read off what they share

`merge_nodes` turns records with the same `share_key` into one node. Because our
language keys are stable URLs, we also keep a small lookup from URL to language name so
the merged result remains readable. The `count` column tells us how many original
records were brought together:

```python
language_names = {
    r["raw_id"]: r["name"]
    for r in tagged.select(entity_types=["Language"]).entity_records(columns=["raw_id", "name"])
}

merged = keyed.merge_nodes(by="share_key").annotate_entities(
    name=lambda e: language_names.get(e.id, e.id)
)
shared = [r for r in merged.entity_records(columns=["name", "count"]) if r["count"] > 1]
sorted(shared, key=lambda r: -r["count"])
```

```
[{'name': 'Efate, South', 'count': 3},
 {'name': 'Bislama', 'count': 2}]
```

Efate, South has a count of **3**: all three collections document it. Bislama, the
national creole, turns up in two. The names are for display; the actual matching still
used the OLAC language URLs in `raw_id`. `merge_nodes` gives you a summary view of the
overlap, which is exactly what you want for the question "which languages do these
collections have in common?".

This result follows from the match we chose. If we used `raw_id` for every kind of
record, people and institutions would join too. If we wanted to compare places, there
would be no simple shared id; we would need to compare the geography instead.

Draw the merged graph the same way we drew the first one. Merging dropped the `origin`
we added earlier, but we can read it back off each node's id: a node that stayed unique
still wears its `NT1/` prefix, while a merged language node does not, so we label those
`"shared"`:

```python
crates = {"NT1", "NT8", "BR1"}

def merged_origin(e):
    head = e.id.split("/")[0]
    return head if head in crates else "shared"

merged.annotate_entities(origin=merged_origin).visualise(
    colour_by="origin", simple=True,
    filepath="paradisec-merged-network.html")
```

<iframe src="../../assets/paradisec-merged-network.html" width="100%" height="480"
        style="border:none" loading="lazy" scrolling="no" title="The three crates joined through their shared languages after merging"></iframe>

The three islands are now **one connected graph**. The shared language nodes act as
bridges between the coloured collection clusters: South Efate connects all three crates,
and Bislama connects NT1 and BR1. That is the payoff of the merge. The shared language is
no longer copied three times; it is one point of connection between the collections.

## 5. A map that hints at another possible join

The crates agree on the language. Do they agree on the *place*? Each one records a
South Efate location as a bounding box (its coordinates reached through the same
Well-Known Text link the [mapping tutorial](mapping-collection-places.md) follows).
Plotting those boxes coloured by crate gives a quick look at how the collections sit in
space:

??? note "Show the map-drawing code"

    The drawing is incidental to the merge story, so it is tucked away here. The boxes
    turn out to be *nested* (one crate covers the whole island, another a single
    village), so we draw the largest first with a faint fill and solid borders, or the
    big box would simply hide the small ones.

    ```python
    import plotly.graph_objects as go
    from shapely import wkt

    def place_wkt(e):
        """A place's WKT, on the place itself or on a linked Geometry."""
        raw = (e.get("asWKT") or e.get("geo:asWKT")
               or e.related("geo").first(key="asWKT")
               or e.related("geo").first(key="geo:asWKT"))
        return (raw[0] if isinstance(raw, list) else raw) if raw else None

    def hex_to_rgba(colour, alpha):
        """A faint fill from a solid hex colour, so nested boxes stay distinguishable."""
        h = colour.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r}, {g}, {b}, {alpha})"

    located = tagged.annotate_entities(wkt=place_wkt).select(entity_types=["Place"])
    origin_colours = {"NT1": "#c1272d", "NT8": "#1f77b4", "BR1": "#6a3d9a"}

    # Largest box first, so the smaller ones end up drawn on top and stay visible.
    boxes = [(wkt.loads(r["wkt"]), r["origin"])
             for r in located.entity_records(columns=["origin", "wkt"]) if r["wkt"]]
    boxes.sort(key=lambda b: -b[0].area)

    fig = go.Figure()
    for poly, origin in boxes:
        xs, ys = poly.exterior.xy
        fig.add_trace(go.Scattermap(
            lon=list(xs), lat=list(ys), mode="lines", fill="toself",
            name=origin, line=dict(color=origin_colours[origin], width=3),
            fillcolor=hex_to_rgba(origin_colours[origin], 0.12)))
    fig.update_layout(
        map=dict(style="open-street-map", center=dict(lat=-17.72, lon=168.33), zoom=8.5),
        height=480, margin=dict(l=0, r=0, t=0, b=0), legend_title_text="Origin crate")
    fig.show()
    ```

<iframe src="../../assets/paradisec-bbox-map.html" width="100%" height="480"
        style="border:none" loading="lazy" scrolling="no" title="South Efate place footprints coloured by crate"></iframe>

The three boxes sit over the same stretch of Efate, nested inside one another at
different resolutions, but they are not the same box, and each crate gives its place a
different id. Unlike the language records, there is no shared identifier that says
"these places are the same". A researcher would have to decide whether nested or
overlapping boxes should count as the same place. The map is enough to show the
opportunity is real, and also why a place-based connection is a distinct research
direction from the language merge.

## Next steps

Merging on language is the simplest case because the crates already shared an identifier,
but it is only one defensible connection. Using `raw_id` for **every** kind of record
would also bring together the people and institutions these collections have in common
(both NT crates share Nick Thieberger; all three share PARADISEC and the University of
Melbourne). From here, pair this with
[Visualising a collection](visualising-a-collection.md) to explore the joined graph, or
[Mapping the places in a collection](mapping-collection-places.md) to take the place
reconciliation further.
