<!--
Case study (draft). Code below was run against data/ohrm/EOASI2022-ro-crate on 2026-06-27;
the outputs shown are real. Figures render to docs/assets/eoas-women-* via
scripts/notebook_to_casestudy.py; regenerate them if the crate or code changes.
-->

# Women in the Encyclopedia of Australian Science (EOAS)

The [Encyclopedia of Australian Science and Innovation](https://www.eoas.info) (EOAS) is a
biographical register of people, organisations and resources from the history of Australian
science. This register is saved locally in RO-Crate.

This notebook takes us through a set of research questions about the **women** recorded
in the collection, using `crategraph` for the graph exploration and handing tabular summaries to pandas/Plotly where charts or cross-tabs are clearer.

**Research questions**

1. Who is the first woman recorded in this collection: a pioneer, or an artefact of sparse early data?
2. Did these women come from educated families?
3. When did the *boom* of female scientists happen?
4. Which fields attracted women most?
5. Are there demographic patterns among them?
6. What is the highest share of women vs men recorded at any point in time?
7. Can we see era trends in their choice of fields?

The notebook is organised into four parts: **§1 a clean dataset**, **§2 timing**, **§3 fields**,
and **§4 backgrounds**, closing with a bonus network of shared honours.

!!! note "Draft case study"

    This case study is an early draft. The analysis is sound and the outputs are real,
    but upcoming refinements will further improve the code and language clarity.

## What you'll learn

- How to build a trustworthy subset of a collection and screen it for data-quality traps.
- How to count and rank values across the collection, including fields that hold several
  values at once.
- How to work with messy historical dates and read trends over time.
- How to follow the links between records to bring in facts about related people.
- How to turn part of a collection into a network diagram and pick out its key figures.

## Running this tutorial

Install crategraph with Jupyter and the plotting dependencies, then launch a notebook:

```bash
python -m pip install crategraph jupyter pandas plotly kaleido
jupyter notebook
```

## 1. Building a community of women

Every later question depends on one thing: a trustworthy set of "the women in EOAS". First,
we need to understand how gender is recorded, and rule out a couple of data-quality
traps. Let's load the crate.

```python
from crategraph import Crate
import pandas as pd
import plotly.express as px

crate = Crate("data/ohrm/EOASI2022-ro-crate")
crate
```

```
Graph(43255 entities, 95052 relationships, source='data/ohrm/EOASI2022-ro-crate')
```


### How is gender recorded?

We ask crategraph to count the values of the `gender` property directly with `entity_counts`.

```python
crate.entity_counts("gender")
```

| gender | count |
| --- | --- |
| M | 5126 |
| F | 892 |
| m | 9 |
| f | 2 |


We flag each person's gender once on the crate with `annotate_entities`, adding derived
`is_female` and `is_male` columns. From here we can slice the women (and later the men) with a
simple `where`, no need to re-derive the test each time.

```python
crate = crate.annotate_entities(
    is_female=lambda entity: (entity.get("gender") or "").lower() == "f",
    is_male=lambda entity: (entity.get("gender") or "").lower() == "m",
)

fem = crate.where(is_female=True)
```


### Data-quality check: do archivists appear in this set?

EOAS records the archivists who *prepared* entries. They appear as the target of a `preparedBy`
relationship. If any archivist also carried a `gender` value, they would appear in our
dataset (however that's not desired). We test this directly: flag anything with an **incoming** `preparedBy` edge as an
archivist, and see whether removing them changes the count.

```python
fem_archivist = crate.annotate_entities(
    is_archivist=lambda e: e.has("preparedBy", direction="in"),
).where(is_female=True).where(is_archivist=True)

len(fem_archivist)
```

```
0
```


We *verified* that there are no archivists carrying a female gender value, so we can consider our `fem` dataset clean.

### Data-quality check: `function` vs `x_efunction`

EOAS stores a person's profession in two properties, `function` and `x_efunction`. They mostly
agree, but not entirely. We compare how many of the dataset have each one populated, so we know
which to trust for the field analysis in §3.

```python
profession_coverage = fem.annotate_entities(
    has_function=lambda entity: bool(entity.get("function")),
    has_xefunction=lambda entity: bool(entity.get("x_efunction")),
)

with_function = profession_coverage.where(has_function=True)
with_xefunction = profession_coverage.where(has_xefunction=True)

coverage_summary = {
    "women with function": len(with_function),
    "women with x_efunction": len(with_xefunction),
    "women missing function": len(fem) - len(with_function),
}
coverage_summary
```

```
{'women with function': 871,
 'women with x_efunction': 672,
 'women missing function': 23}
```


Coverage alone is not enough to choose a field. Next, separate real disagreement from simple missingness: some records have `function` but no `x_efunction`, and those should not be treated as conflicting values.

```python
def function_overlap(entity):
    function = entity.get("function")
    x_efunction = entity.get("x_efunction")
    if function and x_efunction:
        return "both, same" if function == x_efunction else "both, different"
    if function:
        return "function only"
    if x_efunction:
        return "x_efunction only"
    return "neither"


# label each woman by how her two profession fields relate, then tally
profession_overlap = fem.annotate_entities(function_overlap=function_overlap)
real_function_mismatches = profession_overlap.where(function_overlap="both, different")

profession_overlap.entity_counts("function_overlap")
```

| function_overlap | count |
| --- | --- |
| both, same | 654 |
| function only | 199 |
| neither | 23 |
| both, different | 18 |


No woman has `x_efunction` without `function`, and only 18 women have both fields populated with different values. Inspect those real mismatches before settling on the profession field.

```python
pd.DataFrame(
    real_function_mismatches.entity_records(columns=["name", "function", "x_efunction"])
).head(10)
```

|  | name | function | x_efunction |
| --- | --- | --- | --- |
| 0 | Hobler, Mabel Theodore | Zoological collector | Zoological collector, |
| 1 | Scarth-Johnson, Vera | Botanical collector, Botanical artist | Botanical collector, Botanical illustrator |
| 2 | Eardley, Constance Margaret | Botanist, Educator | Botanist |
| 3 | Meredith, Louisa Ann | Author, Botanical artist | Author |
| 4 | Lloyd, Elizabeth Gertrude (Beth) | Dietician | Dietician, Dietician |
| 5 | Livingstone, Catherine Brighid | Accountant, Science administrator | Accountant |
| 6 | Ladiges, Pauline Yvonne | Botanist, Phylogenetic systematist, Taxonomist | Botanist |
| 7 | Workman, Barbara Skeete | Medical administrator, Medical educator | Medical educator |
| 8 | Turner, Susan | Science historian, Geologist | Historian, Geologist |
| 9 | McMillen, Isabella Caroline | Physiologist, University Administrator | Physiologist |


The check supports using `function`: it covers every `x_efunction` record and carries more detail for most women. Now split `function` into one role per value, because many people hold more than one role.

```python
# `entity_counts` explodes list-valued fields, so annotate each woman with a
# list of roles and let crategraph tally the split values.
fem_roles = fem.annotate_entities(
    roles=lambda entity: [
        role.strip()
        for role in (entity.get("function") or "").split(",")
        if role.strip()
    ]
)
prof_counts = fem_roles.entity_counts("roles")
prof_counts
```

| roles | count |
| --- | --- |
| Educator | 90 |
| Nurse | 77 |
| Physician | 59 |
| Botanist | 45 |
| Nurse educator | 39 |
| Botanical collector | 36 |
| Company director | 23 |
| Ornithologist | 21 |
| Teacher | 21 |
| Biochemist | 19 |
| Botanical artist | 19 |
| Nurse administrator | 19 |
| Physicist | 18 |
| Author | 17 |
| Medical administrator | 17 |
| Naturalist | 17 |
| Zoologist | 16 |
| Pathologist | 15 |
| Chemist | 14 |
| Anthropologist | 13 |

*Showing 20 of 269 rows*


```python
professions = pd.Series({row["roles"]: row["count"] for row in prof_counts})
top_professions = professions.head(20).sort_values()

fig = px.bar(
    x=top_professions.values,
    y=top_professions.index,
    orientation="h",
    title="Top 20 professions among women in EOAS",
    labels={"x": "Number", "y": "Profession"},
)
fig.update_traces(marker_color="#008080")
fig.update_layout(
    template="plotly_white",
    height=400,
    margin=dict(l=10, r=30, t=50, b=10),
)
fig.show()
```

<iframe src="../../assets/eoas-women-1.html" width="100%" height="420"
        style="border:none" loading="lazy" title="figure"></iframe>


```python
print(
    f"{len(with_function)} women hold {professions.sum()} roles "
    f"across {len(professions)} distinct professions."
)
```

```
871 women hold 1237 roles across 269 distinct professions.
```


At the other end of the distribution, find the least common professions. These one-person categories are useful for browsing, but they are too sparse to support much aggregate interpretation.

```python
lowest_count = professions.min()
least_common_professions = professions[professions == lowest_count]
len(least_common_professions)
```

```
131
```


```python
list(least_common_professions.index)
```

```
['Acarologist',
 'Accountant',
 'Actuary',
 'Aeronautical engineer',
 'Agricultural educator',
 'Agriculturalist',
 'Aquatic Scientist',
 'Architect',
 'Archivist',
 'Army matron-in-chief',
 'Bibliographer',
 'Biogeographer',
 'Biophysicist',
 'Chemical physicist',
 'Child welfare worker',
 'Civil engineer',
 'Clerk',
 'Community service',
 'Computational physicist',
 'Conchologist',
 'Conservation geneticist',
 'Crystallographer',
 'Cytogeneticist',
 'Demographer',
 'Dental surgeon',
 'Earth scientist',
 'Economist',
 'Ecotoxicologist',
 'Educational administrator',
 'Educationist',
 'Endocrinologist',
 'Engineering teacher',
 'Environmental Historian',
 'Environmentalist',
 'Ethnobotanist',
 'Ethnologist',
 'Eucalypt geneticist',
 'Evolutionary biologist',
 'Food scientist',
 'Forensic psychologist',
 'Forest scientist',
 'Freshwater biologist',
 'Geophysicist',
 'Governor',
 'Grazier',
 'Health care researcher',
 'Health worker',
 'Histologist',
 'Industrial chemist',
 'Information technologist',
 'Inventor',
 'Journalist',
 'Judge',
 'Malacologist',
 'Manufacturer',
 'Marine Science',
 'Marine micropalaeontologist',
 'Marine zoologist',
 'Mathematical physicist',
 'Mathematics teacher',
 'Medical mycologist',
 'Medical officer',
 'Medical research scientist',
 'Medical social worker',
 'Micropalaeontologist',
 'Mineral chemist',
 'Molecular biologist',
 'Molecular oncologist',
 'Museum administrator',
 'Museum director',
 'Mycologist',
 'Natural history photographer',
 'Nephrologist',
 'Neuroanatomist',
 'Nun',
 'Nurse manager',
 'Nutrition scientist',
 'Nutritional physiologist',
 'Occupational hygienist',
 'Oncologist',
 'Operations researcher',
 'Orthopaedic surgeon',
 'Paediatric Gastroenterologist',
 'Palynologist',
 'Pastoralist',
 'Philanthropist',
 'Photographer',
 'Physical chemist',
 'Plant Biochemist',
 'Plant biologist',
 'Plant breeder',
 'Plant ecologist',
 'Plant evolutionary biologist',
 'Plant geneticist',
 'Plastic surgeon',
 'Postmistress',
 'Radiotherapist',
 'Rangeland Ecologist',
 'Research scientist',
 'Rheumatologist',
 'Scholar',
 'School teacher',
 'Science biographer',
 'Science writer',
 'Scientific editor',
 'Secretary',
 'Social anthropologist',
 'Social worker',
 'Software engineer',
 'Soil scientist',
 'Spectrochemist',
 'Taxonomist',
 'Thoracic surgeon',
 'Toxinologist',
 'Unknown',
 'Veterinarian',
 'Veterinary scientist',
 'Vice-Chancellor',
 'Virologist',
 'Viticulturist',
 'Wildlife photographer',
 'Wireless expert',
 'Zoo director',
 'Zoological artist',
 'army nurse',
 'bioinformatician',
 'headmistress',
 'health visitor',
 'materials scientist',
 'orthopaedist',
 'sanitary inspector']
```


There are 131 professions linked to only one woman each in this dataset.

## 2. Timing — when did these women live?

`startDate` on a person is their birth date, but it's stored as a messy string. `convert_dates()` parses it for us and adds a clean `year`. We can now answer the question about the first woman in this dataset:

```python
fem_dates = fem.convert_dates(start="startDate", report=False)
```


### The first woman recorded

Get the first entry in chronologically sorted dataset:

```python
# sort the dated women by birth year; the earliest on record is first
by_birth = sorted(
    (r for r in fem_dates.entity_records(columns=["name", "year", "function"]) if r["year"]),
    key=lambda r: r["year"],
)
by_birth[0]
```

```
{'name': 'Knip, Pauline de Courcelles',
 'year': 1781,
 'function': 'Natural history artist'}
```


Pauline de Courcelles Knip was a natural history artist. This earliest record sits well before the cluster of later ones: it's a starting point, and not necessarily proof that she was a pioneer.

### When did the boom happen?

Counting births by year shows when women start appearing in numbers.

```python
# births by year as a clean frame for the histogram and the share-over-time view
years = pd.DataFrame(fem_dates.entity_records(columns=["year"])).dropna()
years["year"] = years["year"].astype(int)
```


```python
fig = px.histogram(
    years, x="year", nbins=30,
    title="Women in EOAS by birth year",
)
fig.update_traces(marker_color="#008080")
fig.update_layout(template="plotly_white", height=400, margin=dict(l=10, r=30, t=50, b=10))
fig.show()
```

<iframe src="../../assets/eoas-women-2.html" width="100%" height="420"
        style="border:none" loading="lazy" title="figure"></iframe>


### Women vs men over time

To see the *share* of women, we build the men's dataset the same way and compare births per decade.

```python
men = crate.where(is_male=True)
men_dates = men.convert_dates(report=False)

years["decade"] = (years["year"] // 10) * 10

myears = pd.DataFrame(men_dates.entity_records(columns=["year"])).dropna()
myears["year"] = myears["year"].astype(int)
myears["decade"] = (myears["year"] // 10) * 10

women_by_decade = years["decade"].value_counts().rename("women")
men_by_decade = myears["decade"].value_counts().rename("men")

decade_counts = pd.concat([women_by_decade, men_by_decade], axis=1).fillna(0).astype(int)
decade_counts = decade_counts.sort_index()
decade_counts["% women"] = (
    100 * decade_counts["women"] / (decade_counts["women"] + decade_counts["men"])
).round(1)

share = decade_counts["% women"].dropna()
decade_counts.tail(12)
```

|  | women | men | % women |
| --- | --- | --- | --- |
| decade |  |  |  |
| 1900 | 64 | 408 | 13.6 |
| 1910 | 88 | 460 | 16.1 |
| 1920 | 81 | 480 | 14.4 |
| 1930 | 71 | 345 | 17.1 |
| 1940 | 116 | 264 | 30.5 |
| 1950 | 71 | 94 | 43.0 |
| 1960 | 14 | 37 | 27.5 |
| 1970 | 10 | 16 | 38.5 |
| 1980 | 0 | 8 | 0.0 |
| 1990 | 0 | 8 | 0.0 |
| 2000 | 0 | 2 | 0.0 |
| 2010 | 0 | 3 | 0.0 |


```python
fig = px.line(
    x=share.index, y=share.values, markers=True,
    title="Share of women among dated EOAS people, by decade",
    labels={"x": "decade", "y": "% women"},
)
fig.update_traces(line_color="#008080")
fig.update_layout(template="plotly_white", height=400, margin=dict(l=10, r=30, t=50, b=10))
fig.show()
```

<iframe src="../../assets/eoas-women-3.html" width="100%" height="420"
        style="border:none" loading="lazy" title="figure"></iframe>


The largest birth cohort of dated women is the 1940s, with 116 women. The highest share of women among dated EOAS people is later: 43.0% in the 1950s.

## 3. Era trends in fields

Do the fields women enter change over time? We join each woman's profession to her decade. Because a woman can hold several roles, we split `function` again and keep one row per role.

```python
# one row per (woman, profession) with her decade
era = pd.DataFrame(fem_dates.entity_records(columns=["function", "year"])).dropna()
era["year"] = era["year"].astype(int)
era["decade"] = (era["year"] // 10) * 10
era = era.assign(function=era["function"].str.split(", ")).explode("function")
len(era)
```

```
1013
```


```python
# how the top 5 professions rise and fall across decades
top5 = era["function"].value_counts().head(5).index
sub = era[era["function"].isin(top5)]
counts = sub.groupby(["decade", "function"]).size().reset_index(name="count")

fig = px.line(
    counts, x="decade", y="count", color="function", markers=True,
    title="Top 5 professions of women over time",
)
fig.update_layout(template="plotly_white", height=450, margin=dict(l=10, r=30, t=50, b=10))
fig.show()
```

<iframe src="../../assets/eoas-women-4.html" width="100%" height="470"
        style="border:none" loading="lazy" title="figure"></iframe>


## 4. Backgrounds

### Did they come from educated families?

First, let's count how many family links exist before trying to answer.

```python
fem.relationship_types
```

```
TypeRegistry([Child, Collaborator, Colleague, Parent, Related, Sibling])
```


```python
for r in ["Parent", "Child", "Sibling", "Related"]:
    print(r, len(fem.select(relationship_types=r).relationships))
```

```
Parent 6
Child 6
Sibling 14
Related 6
```


```python
# the .related() idiom: for each woman, follow her Parent links and collect
# any profession recorded on the relative at the other end
family = fem.annotate_entities(
    parent_jobs=lambda e: e.related("Parent", direction="any").join("function"),
    has_parent_job=lambda e: bool(e.related("Parent", direction="any").join("function")),
).where(has_parent_job=True)

family.entity_records(columns=["name", "parent_jobs"])
```

| name | parent_jobs |
| --- | --- |
| Wehl, Louise Therese | Botanical collector |
| Wehl, Marie Magdalene | Botanical collector |
| Wehl, Clara Christine Maria | Botanical artist, Plant collector, Botanical collector |


The family links are very sparse: only a handful across 894 women, and the few that exist connect members of the same scientific family (the Wehls, all botanical collectors) rather than independent women from educated backgrounds. So the dataset can't really tell us whether these women came from educated families; we note it as a limitation rather than forcing an answer.

### Demographic patterns

Where were these women born? `birthState` and `nationality` are well populated, so we can count them directly with `entity_counts`.

```python
fem.entity_counts("birthState")[:10]
```

```
[{'birthState': '#New South Wales', 'count': 156},
 {'birthState': '#Victoria', 'count': 151},
 {'birthState': '#Queensland', 'count': 53},
 {'birthState': '#South Australia', 'count': 42},
 {'birthState': '#Western Australia', 'count': 41},
 {'birthState': '#Tasmania', 'count': 16},
 {'birthState': '#Yorkshire', 'count': 6},
 {'birthState': '#Kent', 'count': 4},
 {'birthState': '#Surrey', 'count': 4},
 {'birthState': '#Lancashire', 'count': 3}]
```


```python
fem.entity_counts("nationality")[:10]
```

```
[{'nationality': '#Australian', 'count': 139}]
```


```python
states = pd.DataFrame(fem.entity_counts("birthState")[:10]).sort_values("count")

fig = px.bar(
    states, x="count", y="birthState", orientation="h",
    title="Where women in EOAS were born (top 10)",
)
fig.update_traces(marker_color="#008080")
fig.update_layout(template="plotly_white", height=400, margin=dict(l=10, r=30, t=50, b=10))
fig.show()
```

<iframe src="../../assets/eoas-women-5.html" width="100%" height="420"
        style="border:none" loading="lazy" title="figure"></iframe>


## Bonus: a network of shared honours

§4 found the family links too sparse to lean on. Recognition is richer. EOAS records awards in
two forms: a per-person award *event* (one node per recipient) and the named medal itself (an
`Award` entity that several people point to). The named medals are the shared ones, so they make
the hubs of a recognition network: women cluster around the honours they have in common.

Women are linked to a medal by the `Related` edge. We expand the women one hop along `Related`,
keep the named medals (an `Award` type that is *not* also a `Person`, which rules out the
per-person events), and keep only medals shared by at least two women so the picture stays legible.

```python
women_plus_related = fem.expand(depth=1, via="Related")
women_plus_related
```

```
Graph(1149 entities, 1581 relationships, source='data/ohrm/EOASI2022-ro-crate')
```


First identify which related entities are named medals. The per-person award events also carry `Award`, so the extra `Person` check keeps only the shared honour nodes.

```python
with_medal_flags = women_plus_related.annotate_entities(
    is_medal=lambda entity: "Award" in entity.types and "Person" not in entity.types
)
with_medal_flags.where(is_medal=True).entity_records(columns=["name", "types"])
```

| name | types |
| --- | --- |
| Tom Vallance Medal | Award |
| Australia Prize | Award |
| M A Sargent Medal | Award |
| R. M. Johnston Memorial Medal | Award |
| Leighton Memorial Medal | Award |
| Australian Natural History Medallion | Award |
| Mueller Medal | Award |
| Walter Burfitt Prize | Award |
| Lemberg Medal and Oration | Award |
| Clarke Medal | Award |
| Frank Fenner Prize for Life Scientist of the Year | Award |
| Nancy T. Burbidge Medal | Award |
| Thomas Ranken Lyle Medal | Award |
| Malcolm McIntosh Prize for Physical Scientist of the Year | Award |
| Pawsey Medal | Award |
| Gottschalk Medal | Award |
| Edgeworth David Medal | Award |
| W. H. (Beattie) Steel Medal | Award |
| Archibald Liversidge Medal and Lecture | Award |
| Prime Minister's Prize for Science | Award |

*Showing 20 of 32 rows*


Then keep all women plus medals won by at least two women, and drop isolated women whose medals were not shared.

```python
shared_honour_candidates = with_medal_flags.annotate_entities(
    keep=lambda entity: bool(entity.get("is_female"))
    or (
        entity.get("is_medal")
        and len(entity.related("Related", direction="any")) >= 2
    )
)

shared_honours = shared_honour_candidates.where(keep=True)
honours = shared_honours.select(min_connections=1)
honours
```

```
Graph(118 entities, 220 relationships, source='data/ohrm/EOASI2022-ro-crate')
```


The most-shared honours, by how many women in the set won each:

```python
[(medal.properties["name"], winners)
 for medal, winners in honours.most_connected(n=8, entity_types=["Award"])]
```

```
[('Australian Natural History Medallion', 13),
 ('Mueller Medal', 7),
 ('Clarke Medal', 6),
 ('Australia Prize', 5),
 ('Malcolm McIntosh Prize for Physical Scientist of the Year', 5),
 ('Lemberg Medal and Oration', 5),
 ('D. L. Serventy Medal', 4),
 ('ANZAAS Medal', 4)]
```


The Australian Natural History Medallion is the clear hub, won by 13 of these women, with the
Mueller and Clarke Medals behind it. Colouring by entity type below separates the women from the
medals: the largest nodes are the most-shared honours, and a woman sitting between two medals is
one who won both.

```python
honours.visualise(colour_by="type", size_by="connections", collapse_edges=True)
```

<iframe src="../../assets/eoas-women-6.html" width="100%" height="600"
        style="border:none" loading="lazy" title="network"></iframe>


## Conclusion

Across the seven questions: we built a verified dataset of **894 women**, found that the
"first" woman reflects where the records start more than a true pioneer, saw when women began
appearing in numbers and how their share shifted over time, watched the mix of fields change
by decade, and looked at where they were born, while noting the family data is too sparse to
say much about their backgrounds. Finally, a network of shared honours showed recognition clustering around a handful of medals, with the Australian Natural History Medallion linking the most women.

## Next steps

- This case study leans on the dates idiom from
  [Exploring temporal dimensions of RO-Crates](../tutorials/exploring-temporal-dimensions.md);
  try drawing a lifespan timeline from each woman's `startDate` and `endDate`, or colouring the
  birth-year histogram by field.
- The shared-honours network used `expand()` and `visualise()`; see
  [Visualising a collection](../tutorials/visualising-a-collection.md) to colour it by community
  or size it differently, or build the denser co-profession network instead.
- Because `entity_records()` produces plain rows, the tables here feed straight into the
  [From Graph to DataFrame](../tutorials/from-graph-to-dataframe.md) workflow: group by decade,
  write a CSV, or join these facts onto other analysis.
