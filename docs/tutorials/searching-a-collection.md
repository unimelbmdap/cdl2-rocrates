# Searching a collection

A collection answers different questions with different kinds of search. If you half-remember
a name, you want a quick, approximate match over the metadata. If you want to find where a
topic comes up, you need to search the actual text by meaning. `crategraph` offers both, and
this tutorial shows when to reach for each.

We'll use the **Australian Radio Talkback** collection: transcripts of talkback segments from
ABC and commercial radio, wrapped in metadata about the presenters, callers, and shows. The
metadata layer is what fuzzy search matches; the transcripts are what semantic search reads.

## What you'll learn

- Fuzzy search over a collection's metadata, and tuning it with `threshold` and `properties`.
- Building a semantic index and searching the transcript text by meaning.
- Which kind of search fits which question.

## Running this tutorial

Semantic search needs the `[index]` extra. Install it with Jupyter, then launch a notebook:

```bash
python -m pip install "crategraph[index]" jupyter
jupyter notebook
```

The first semantic search builds an index, which downloads a small (~50 MB) embedding model
once and then runs entirely on your machine. Building the index also takes a little time, on
the order of a minute or two for a collection this size, since it embeds every transcript;
larger collections take proportionally longer. Fuzzy search needs none of this and is instant.

## 1. Load the crate

```python
from crategraph import Crate

crate = Crate("data/ldaca/Australian Radio Talkback")
crate
```

```
Graph(452 entities, 918 relationships, source='data/ldaca/Australian Radio Talkback')
```

The crate holds two layers we can search: metadata about 323 `Person` entities (presenters and
callers) and the shows, and the transcript text those records describe.

## 2. Find things by name: fuzzy search

The quickest search is a fuzzy match over the metadata. It matches strings that are similar
rather than identical, runs instantly, and needs no setup. Suppose you half-remember a
presenter's name:

```python
crate.search("Sandy McCutchin")
```

```
Found 3 matches for "Sandy McCutchin":

   93  arcp://…/person/Presenter#Sandy_McCutcheon  (name: Sandy McCutcheon)
   80  arcp://…/object/Nat1  (ldac:speaker: ['arcp://…/person/Presenter#Sandy_McCutcheon', …)
   80  arcp://…/object/Nat2  (ldac:speaker: ['arcp://…/person/Presenter#Sandy_McCutcheon', …)
Graph(3 entities, 2 relationships, source='data/ldaca/Australian Radio Talkback')
```

Despite the misspelling, fuzzy search finds the presenter Sandy McCutcheon, scoring the match
93 out of 100. It also returns two show objects, though: by default the search scans *every*
property, and these shows' `ldac:speaker` field *references* the presenter. `search()` returns
a `Graph` (a subgraph of the matches), so you can chain `where`, `entity_records`, and the rest
of the API onto the result.

### Focus the search with `properties`

To match only the field you mean, pass `properties`. Restricting the search to `name` drops the
two shows and leaves the single presenter:

```python
crate.search("Sandy McCutchin", properties=["name"])
```

```
Found 1 match for "Sandy McCutchin":

   93  arcp://…/person/Presenter#Sandy_McCutcheon  (name: Sandy McCutcheon)
Graph(1 entities, 0 relationships, source='data/ldaca/Australian Radio Talkback')
```

### Tune the cutoff with `threshold`

Each match carries a score, and `threshold` (0 to 100, default 80) sets the bar. Searching for
`Peters` over names returns the broadcaster Pam Peters and, more loosely, a caller named Peter:

```python
crate.search("Peters", properties=["name"])
```

```
Found 2 matches for "Peters":

  100  http://nla.gov.au/nla.party-556106  (name: Pam Peters)
   91  arcp://…/person/Caller#Peter  (name: Peter)
```

The printed scores show why: `Peter` scores 91. Raise the bar above it to keep only the close
match:

```python
crate.search("Peters", properties=["name"], threshold=92)
```

```
Found 1 match for "Peters":

  100  http://nla.gov.au/nla.party-556106  (name: Pam Peters)
```

Lower the threshold to cast a wider net, raise it to be strict. `top_n` (default 10) caps how
many matches come back.

## 3. Find things by meaning: semantic search

Fuzzy search matches the *spelling of metadata*. It never reads the transcripts, and it won't
help you find *where a topic is discussed*. For that, semantic search embeds the transcript
text and retrieves passages by meaning.

!!! info "Embeddings and embedding models, in brief"

    An **embedding** is a list of numbers that captures the meaning of a piece of text, placing
    it as a point in a "meaning space" where passages about similar things sit close together,
    regardless of the exact words they use. An **embedding model** is the trained model that
    reads text and produces those numbers; semantic search runs it once over every transcript
    to build the index, then again over your query so it can return the passages that sit
    nearest. The model used here is small (~50 MB) and runs entirely on your own machine.

First, narrow to the clean transcript files (each recording has a `-plain.txt` derivative
alongside its raw and CSV versions), the same way the
[NLP tutorial](basic-nlp-with-text-records.ipynb) does:

```python
transcripts = crate.annotate_entities(
    is_plain_text=lambda e: "File" in e.types and e.id.endswith("-plain.txt")
).where(is_plain_text=True)
transcripts
```

```
Graph(29 entities, 0 relationships, source='data/ldaca/Australian Radio Talkback')
```

Build a semantic index over those transcripts. This is the step that downloads the embedding
model on first run, then embeds every transcript, so expect it to run for a minute or two on a
collection this size (longer on bigger ones). It only needs doing once: the index is written to
`store_path` and reused by later searches.

```python
transcripts.build_semantic_index(store_path="radio-index.db")
```

```
IndexerStats(sources_indexed=['Australian Radio Talkback'], sources_skipped=[],
             sources_removed=[], total_chunks=1341, total_entities=29)
```

Now search by meaning. Asking about the property market surfaces the real-estate segments,
even though they don't use those exact words:

```python
hits = transcripts.search(
    "house prices and the property market", mode="semantic", store_path="radio-index.db"
)
[entity.id for entity in hits.entities]
```

```
['NAT1-plain.txt', 'COME2-plain.txt', 'COMNE7-plain.txt', 'COMNE3-plain.txt']
```

`search(mode="semantic")` hands back the matching transcripts as a subgraph. To see the actual
passage that matched, and how strongly, use `chunk_records`, which returns ranked text chunks
with scores:

```python
top = next(transcripts.chunk_records(
    "house prices and the property market", store_path="radio-index.db", k=1
))
top["entity_id"], round(top["score"], 3), top["text"][:160]
```

```
('COME2-plain.txt', 0.58,
 "house. That's that's one point about real estate. If it's uh you you can't move "
 "the bl the block of land if   where it is is where it is and that's will get the")
```

## 4. Which search when

| | Fuzzy (`mode="fuzzy"`, the default) | Semantic (`mode="semantic"`) |
| --- | --- | --- |
| Searches | entity **metadata** (property values) | the **text content** of files |
| Good for | a name or title you roughly know | a topic or idea, however it's phrased |
| Tolerates | misspellings, partial matches, and word order | different wording for the same meaning |
| Setup | none (offline, instant) | build an index (one-time model download) |

A rule of thumb: reach for **fuzzy** when you know what something is *called*, and **semantic**
when you know what it's *about*.

## Next steps

A lexical keyword (full-text) search mode is on the roadmap to sit between these two. For now,
the index you built persists at `store_path`, so later searches skip the rebuild, and
`chunk_records` gives you scored passages for ranked retrieval or a search-results view. From
here, [Basic NLP with text records](basic-nlp-with-text-records.ipynb) takes the same
transcripts further, handing their text to NLP tools once search has found the right subset.
