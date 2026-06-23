# Exploring temporal dimensions of RO-Crates

RO-Crates are full of dates, but those dates rarely arrive tidy. The same crate might
record a precise `"22 December 1915"`, a machine timestamp `"1915-12-22 00:00:00"`, a bare
year `"1867"`, a span like `"1902-04"`, or nothing at all in a date field, with the year
hiding in the title instead. This tutorial works through `crategraph`'s temporal features
on the events of a real archival crate, ending with a table and a timeline.

We'll use the **University of Melbourne Perpetual Calendar (UMPC)** crate from the
[OHRM Upload Project](https://figshare.unimelb.edu.au/projects/OHRM_Upload_Project/230466).
It has thousands of entities; we'll focus on its `Event` entities.

## What you'll learn

- Reading the dates off each event without parsing the raw text yourself.
- How crategraph, by default, prefers genuine event dates and ignores record-keeping ones.
- Saving those dates as columns, with a coverage report, using `convert_dates()`.
- Building a table of the dated events.
- Filling in a date by hand for a case crategraph cannot read on its own.
- Drawing an interactive timeline of several entity types with Plotly Express.

## Running this tutorial

While `crategraph` is pre-release, launch from the repository root with `uv run`, pulling in
the project plus the plotting dependencies:

```bash
uv run --all-extras --with jupyter --with pandas --with plotly --with kaleido jupyter notebook
```

## 1. Load the crate and focus on events

```python
from crategraph import Crate

crate = Crate("experiments/crates/UMPC")
crate
```

```
Graph(4270 entities, 12601 relationships, source='experiments/crates/UMPC')
```

`select()` narrows the graph to a single type, and `summary()` reports what is in the result.
Applied to the events:

```python
events = crate.select(entity_types=["Event"])
events.summary()
```

```
=== Graph Summary ===
Source: experiments/crates/UMPC
Entities: 32 | Relationships: 12

Entity types:
  Event  32  ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒

Relationship types:
  Related  12  ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒
```

## 2. Look at the date fields on one event

Before reading any dates, it is worth inspecting the raw material. Pick an event and look at
its date-related properties:

```python
event = events.where(startDate="22 December 1915").entities[0]
{k: event.properties[k] for k in
 ["name", "startDate", "startDateISOString", "endDate", "recordAppendDate"]}
```

```python
{'name': '2015 - Announcement by W. M. Hughes ... creation of the CSIR/CSIRO',
 'startDate': '22 December 1915',
 'startDateISOString': '1915-12-22 00:00:00',
 'endDate': '22 December 1915',
 'recordAppendDate': '2018-11-28 12:13:35'}
```

Three date fields, each with a different role. `startDate` is the date as a person would
write it; `startDateISOString` is the same date in a machine format; and `recordAppendDate`
is a record-keeping date, marking when the entry was added to the catalogue rather than when
the event happened. Anything that simply took the first property with "date" in its name
could return "1915" or "2018" depending on which it reached first. crategraph distinguishes
between them.

## 3. Reading the dates with crategraph

`annotate_entities` adds a new field to every event, computed by a small function we supply
(the `lambda e: ...` is a compact one-line function in which `e` is one event). Inside that
function each event exposes date properties that read its fields, so you do not parse the
raw text yourself:

```python
dated = events.annotate_entities(
    year=lambda e: e.year,
    precision=lambda e: e.date_precision,
)
```

- `e.year`: the year the event starts.
- `e.start_date` / `e.end_date`: the start and end as dates, not text.
- `e.date_precision`: how exact the date is, one of `"day"`, `"month"`, `"year"` or `"decade"`.
- `e.date_circa` / `e.date_uncertain`: flags marking a date as approximate or uncertain.

By default, crategraph reads the event dates, preferring the `startDateISOString` /
`endDateISOString` fields and falling back to the human `startDate` / `endDate`. It does not
read record-keeping dates such as `recordAppendDate`. These properties therefore report when
an event happened, not when it was catalogued.

```python
import pandas as pd

df = pd.DataFrame(dated.entity_records(columns=["label", "year", "precision"]))
df.dropna(subset=["year"]).sort_values("year").head(6)
```

```
                                        label    year precision
1852 - The Victorian Legislative Council ...  1852.0       day
1853 - Sir Redmond Barry appointed the fir... 1853.0       day
1853 - Appointment of the University Council  1853.0       day
1853 - The University Act receives Royal A... 1853.0       day
          1867 - Establishment of the Senate  1867.0       day
                        1901 - Dickson Fraud  1901.0       day
```

### A note on precision

crategraph prefers `startDateISOString` because it is machine-readable, but that field can
be too confident. The Senate event records `startDate: "1867"` (a year only), yet its
`startDateISOString` is `"1867-01-01 00:00:00"`, so by default crategraph reports **day**
precision. When you would rather trust one particular field, `parse_date` reads only the
field you name:

```python
precise = events.annotate_entities(
    default_precision=lambda e: e.date_precision,
    human_precision=lambda e: (
        e.parse_date("startDate").precision if e.parse_date("startDate") else None
    ),
)
pd.DataFrame(precise.entity_records(columns=["label", "default_precision", "human_precision"])) \
    .query("label == '1867 - Establishment of the Senate'")
```

```
                               label default_precision human_precision
  1867 - Establishment of the Senate               day            year
```

Reading the human `startDate` directly returns **year** precision. crategraph does not
fabricate a January 1st that the source never stated.

## 4. Save the dates as columns with `convert_dates()`

Reading dates one at a time suits exploratory work. When you want every date saved as its
own column, together with a report on coverage, use `convert_dates()`:

```python
converted = events.convert_dates()
```

```
convert_dates: parsed 18/18 entities with date fields (100%).
```

Every event with a readable date field now carries `start_date`, `end_date`, `year`,
`date_precision`, `date_circa` and `date_uncertain` columns. The report counts only the
events that *have* a date field, 18 of the 32. The other 14 have no event date at all, and
`convert_dates()` did not infer one from `recordAppendDate`. We address those 14 in step 6.

## 5. Build a table of the dated events

`entity_records()` gives one row per event, ready for pandas. The saved `start_date` and
`end_date` are written as ISO date text, which sorts in date order, so ordering by
`start_date` produces a chronological table rather than an alphabetical one:

```python
df = pd.DataFrame(converted.entity_records(
    columns=["label", "start_date", "end_date", "year", "date_precision"]
))
df = df.dropna(subset=["year"]).sort_values("start_date").reset_index(drop=True)
df.head(6)
```

```
                                        label  start_date    end_date    year date_precision
1852 - The Victorian Legislative Council ...  1852-12-15  1852-12-15  1852.0            day
1853 - Sir Redmond Barry appointed the fir... 1853-01-01  1880-12-31  1853.0            day
1853 - The University Act receives Royal A... 1853-01-22  1853-01-22  1853.0            day
1853 - Appointment of the University Council  1853-04-11  1853-04-11  1853.0            day
          1867 - Establishment of the Senate  1867-01-01  1867-12-31  1867.0            day
                        1901 - Dickson Fraud  1901-01-01  1901-01-01  1901.0            day
```

`year` appears as a decimal (`1852.0`) because the 14 undated events leave the cell blank
and pandas widens the column to hold the gaps; `df["year"].astype("Int64")` gives plain
whole numbers if you prefer. Sir Redmond Barry's row runs from 1853 to 1880, because the
crate records a start-and-end span there and `convert_dates()` keeps both ends.

## 6. Filling in a date by hand

Fourteen events have no usable date field, but their titles carry the year: `"1971 - The
Master Plan"`, `"1944 - Melbourne University Staff Association founded"`. The year is
present, written into the name rather than a date field. No general-purpose reader should
guess that, but within your own crate you know the convention, so you can write a small
function that falls back to the title only when crategraph finds nothing:

```python
import re

def event_year(e):
    if e.year is not None:                       # trust a real date field first
        return e.year
    match = re.match(r"\s*(\d{4})", e.get("name") or "")  # otherwise read the year off the title
    return int(match.group(1)) if match else None

recovered = events.annotate_entities(
    event_year=event_year,
    year_source=lambda e: "date field" if e.year is not None else "recovered from title",
)
```

This keeps the parsed dates and uses the title only as a fallback, recording where each
event's year came from:

```python
df = pd.DataFrame(recovered.entity_records(columns=["label", "event_year", "year_source"]))
df["event_year"].notna().sum(), df["year_source"].value_counts().to_dict()
```

```
(32, {'date field': 18, 'recovered from title': 14})
```

All 32 events now have a year. The same approach handles messier conventions: `parse_year`
understands ranges and circa markers, so a title like `"1902-04 - Fink Royal Commission"`
could be read with `e.parse_year(...)` over a field of your choosing, or you can pass
`convert_dates(parser=...)` your own date reader.

## 7. A timeline across entity types

So far we have used events, but the same date reading applies to every entity in the crate,
so we can broaden the view. We select several kinds of record, let `convert_dates()` read
the year off each, and give every type its own lane. Each entity becomes a point you can
hover over for its title and year. (The title-based recovery in step 6 was specific to those
event names; here we rely on the automatic reading.)

```python
import plotly.express as px

types = ["Event", "Activity", "Organisation", "Academic_Unit"]
dated = crate.select(entity_types=types).convert_dates(report=False)

df = pd.DataFrame(dated.entity_records(columns=["label", "type", "year", "date_precision"]))
df = df.dropna(subset=["year"])
df["date"] = pd.to_datetime(df["year"].astype(int), format="%Y")

fig = px.scatter(
    df, x="date", y="type", color="type", hover_name="label",
    hover_data={"year": True, "date_precision": True, "type": False, "date": False},
    category_orders={"type": types},
    title="University of Melbourne records through time, by type",
)
fig.update_traces(marker=dict(size=11, opacity=0.6))
fig.update_layout(yaxis_title=None, xaxis_title="Year", legend_title=None, height=400)
fig.show()
```

The chart below is interactive: hover over any point to read the entity's title, year and
precision, and use the legend to hide a type.

<iframe src="../../assets/temporal-events-timeline.html" width="100%" height="430"
        style="border:none" loading="lazy" title="Timeline of UMPC records by type"></iframe>

Reading across the lanes, `Academic_Unit` and `Organisation` records accumulate steadily
from the 1850s onward, the few `Event` entities fall across that span, and `Activity`
records, which describe recent project work, cluster in the 2010s.

## Next steps

The same date reading also drives filtering: `crate.select(time_range=(1850, 1900))` keeps
the entities whose dates fall in a window, so you can narrow a collection to a period before
any of the analysis above. Because `convert_dates()` writes plain columns, its output feeds
directly into the [From Graph to DataFrame](from-graph-to-dataframe.md) workflow: group by
decade, write a CSV, or join temporal facts onto the rest of your analysis.
