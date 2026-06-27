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

While `crategraph` is pre-release, launch from the repository root with `uv run`, pulling in the
project plus the plotting dependencies:

```bash
uv run --all-extras --with jupyter,pandas,plotly,kaleido jupyter notebook
```

## 1. Building a community of women

Every later question depends on one thing: a trustworthy set of "the women in EOAS". First,
we need to understand how gender is recorded, and rule out a couple of data-quality
traps. Let's load the crate.

```python
from crategraph import Crate
import pandas as pd
import plotly.express as px

crate = Crate("./data/EOASI2022-ro-crate")
crate
```

```
Graph(43255 entities, 95052 relationships, source='data/EOASI2022-ro-crate')
```


### How is gender recorded?

We ask crategraph to count the values of the `gender` property directly with `entity_counts`.

```python
crate.entity_counts("gender")
```

<div style="font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: #222;"><div style="color: #666; margin-bottom: 2px;">Records: 4 rows x 2 fields</div><table style="border-collapse: collapse; border: none; background: none;"><thead><tr><th style="text-align: left; padding: 1px 12px 3px 0; border: none; border-bottom: 1px solid #ccc; color: #666; font-weight: 600; white-space: nowrap;">gender</th><th style="text-align: left; padding: 1px 12px 3px 0; border: none; border-bottom: 1px solid #ccc; color: #666; font-weight: 600; white-space: nowrap;">count</th></tr></thead><tbody><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">M</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">5126</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">F</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">892</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">m</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">9</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">f</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">2</td></tr></tbody></table></div>


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

<div style="font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: #222;"><div style="color: #666; margin-bottom: 2px;">Records: 4 rows x 2 fields</div><table style="border-collapse: collapse; border: none; background: none;"><thead><tr><th style="text-align: left; padding: 1px 12px 3px 0; border: none; border-bottom: 1px solid #ccc; color: #666; font-weight: 600; white-space: nowrap;">function_overlap</th><th style="text-align: left; padding: 1px 12px 3px 0; border: none; border-bottom: 1px solid #ccc; color: #666; font-weight: 600; white-space: nowrap;">count</th></tr></thead><tbody><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">both, same</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">654</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">function only</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">199</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">neither</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">23</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">both, different</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">18</td></tr></tbody></table></div>


No woman has `x_efunction` without `function`, and only 18 women have both fields populated with different values. Inspect those real mismatches before settling on the profession field.

```python
pd.DataFrame(
    real_function_mismatches.entity_records(columns=["name", "function", "x_efunction"])
).head(10)
```

<div>
<style scoped>
    .dataframe tbody tr th:only-of-type {
        vertical-align: middle;
    }

    .dataframe tbody tr th {
        vertical-align: top;
    }

    .dataframe thead th {
        text-align: right;
    }
</style>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>name</th>
      <th>function</th>
      <th>x_efunction</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>Hobler, Mabel Theodore</td>
      <td>Zoological collector</td>
      <td>Zoological collector,</td>
    </tr>
    <tr>
      <th>1</th>
      <td>Scarth-Johnson, Vera</td>
      <td>Botanical collector, Botanical artist</td>
      <td>Botanical collector, Botanical illustrator</td>
    </tr>
    <tr>
      <th>2</th>
      <td>Eardley, Constance Margaret</td>
      <td>Botanist, Educator</td>
      <td>Botanist</td>
    </tr>
    <tr>
      <th>3</th>
      <td>Meredith, Louisa Ann</td>
      <td>Author, Botanical artist</td>
      <td>Author</td>
    </tr>
    <tr>
      <th>4</th>
      <td>Lloyd, Elizabeth Gertrude (Beth)</td>
      <td>Dietician</td>
      <td>Dietician, Dietician</td>
    </tr>
    <tr>
      <th>5</th>
      <td>Livingstone, Catherine Brighid</td>
      <td>Accountant, Science administrator</td>
      <td>Accountant</td>
    </tr>
    <tr>
      <th>6</th>
      <td>Ladiges, Pauline Yvonne</td>
      <td>Botanist, Phylogenetic systematist, Taxonomist</td>
      <td>Botanist</td>
    </tr>
    <tr>
      <th>7</th>
      <td>Workman, Barbara Skeete</td>
      <td>Medical administrator, Medical educator</td>
      <td>Medical educator</td>
    </tr>
    <tr>
      <th>8</th>
      <td>Turner, Susan</td>
      <td>Science historian, Geologist</td>
      <td>Historian, Geologist</td>
    </tr>
    <tr>
      <th>9</th>
      <td>McMillen, Isabella Caroline</td>
      <td>Physiologist, University Administrator</td>
      <td>Physiologist</td>
    </tr>
  </tbody>
</table>
</div>


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

<div style="font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: #222;"><div style="color: #666; margin-bottom: 2px;">Records: 269 rows x 2 fields</div><table style="border-collapse: collapse; border: none; background: none;"><thead><tr><th style="text-align: left; padding: 1px 12px 3px 0; border: none; border-bottom: 1px solid #ccc; color: #666; font-weight: 600; white-space: nowrap;">roles</th><th style="text-align: left; padding: 1px 12px 3px 0; border: none; border-bottom: 1px solid #ccc; color: #666; font-weight: 600; white-space: nowrap;">count</th></tr></thead><tbody><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Educator</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">90</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Nurse</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">77</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Physician</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">59</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Botanist</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">45</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Nurse educator</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">39</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Botanical collector</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">36</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Company director</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">23</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Ornithologist</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">21</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Teacher</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">21</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Biochemist</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">19</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Botanical artist</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">19</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Nurse administrator</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">19</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Physicist</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">18</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Author</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">17</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Medical administrator</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">17</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Naturalist</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">17</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Zoologist</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">16</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Pathologist</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">15</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Chemist</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">14</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Anthropologist</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">13</td></tr></tbody></table><div style="color: #999; margin-top: 3px;">Showing 20 of 269 rows</div></div>


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

<div>
<style scoped>
    .dataframe tbody tr th:only-of-type {
        vertical-align: middle;
    }

    .dataframe tbody tr th {
        vertical-align: top;
    }

    .dataframe thead th {
        text-align: right;
    }
</style>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>women</th>
      <th>men</th>
      <th>% women</th>
    </tr>
    <tr>
      <th>decade</th>
      <th></th>
      <th></th>
      <th></th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>1900</th>
      <td>64</td>
      <td>408</td>
      <td>13.6</td>
    </tr>
    <tr>
      <th>1910</th>
      <td>88</td>
      <td>460</td>
      <td>16.1</td>
    </tr>
    <tr>
      <th>1920</th>
      <td>81</td>
      <td>480</td>
      <td>14.4</td>
    </tr>
    <tr>
      <th>1930</th>
      <td>71</td>
      <td>345</td>
      <td>17.1</td>
    </tr>
    <tr>
      <th>1940</th>
      <td>116</td>
      <td>264</td>
      <td>30.5</td>
    </tr>
    <tr>
      <th>1950</th>
      <td>71</td>
      <td>94</td>
      <td>43.0</td>
    </tr>
    <tr>
      <th>1960</th>
      <td>14</td>
      <td>37</td>
      <td>27.5</td>
    </tr>
    <tr>
      <th>1970</th>
      <td>10</td>
      <td>16</td>
      <td>38.5</td>
    </tr>
    <tr>
      <th>1980</th>
      <td>0</td>
      <td>8</td>
      <td>0.0</td>
    </tr>
    <tr>
      <th>1990</th>
      <td>0</td>
      <td>8</td>
      <td>0.0</td>
    </tr>
    <tr>
      <th>2000</th>
      <td>0</td>
      <td>2</td>
      <td>0.0</td>
    </tr>
    <tr>
      <th>2010</th>
      <td>0</td>
      <td>3</td>
      <td>0.0</td>
    </tr>
  </tbody>
</table>
</div>


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

<div style="font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: #222;"><div style="color: #666; margin-bottom: 2px;">Records: 3 rows x 2 fields</div><table style="border-collapse: collapse; border: none; background: none;"><thead><tr><th style="text-align: left; padding: 1px 12px 3px 0; border: none; border-bottom: 1px solid #ccc; color: #666; font-weight: 600; white-space: nowrap;">name</th><th style="text-align: left; padding: 1px 12px 3px 0; border: none; border-bottom: 1px solid #ccc; color: #666; font-weight: 600; white-space: nowrap;">parent_jobs</th></tr></thead><tbody><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Wehl, Louise Therese</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Botanical collector</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Wehl, Marie Magdalene</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Botanical collector</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Wehl, Clara Christine Maria</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Botanical artist, Plant collector, Botanical collector</td></tr></tbody></table></div>


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
Graph(1149 entities, 1581 relationships, source='data/EOASI2022-ro-crate')
```


First identify which related entities are named medals. The per-person award events also carry `Award`, so the extra `Person` check keeps only the shared honour nodes.

```python
with_medal_flags = women_plus_related.annotate_entities(
    is_medal=lambda entity: "Award" in entity.types and "Person" not in entity.types
)
with_medal_flags.where(is_medal=True).entity_records(columns=["name", "types"])
```

<div style="font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: #222;"><div style="color: #666; margin-bottom: 2px;">Records: 32 rows x 2 fields</div><table style="border-collapse: collapse; border: none; background: none;"><thead><tr><th style="text-align: left; padding: 1px 12px 3px 0; border: none; border-bottom: 1px solid #ccc; color: #666; font-weight: 600; white-space: nowrap;">name</th><th style="text-align: left; padding: 1px 12px 3px 0; border: none; border-bottom: 1px solid #ccc; color: #666; font-weight: 600; white-space: nowrap;">types</th></tr></thead><tbody><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Tom Vallance Medal</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Australia Prize</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">M A Sargent Medal</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">R. M. Johnston Memorial Medal</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Leighton Memorial Medal</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Australian Natural History Medallion</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Mueller Medal</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Walter Burfitt Prize</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Lemberg Medal and Oration</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Clarke Medal</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Frank Fenner Prize for Life Scientist of the Year</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Nancy T. Burbidge Medal</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Thomas Ranken Lyle Medal</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Malcolm McIntosh Prize for Physical Scientist of the Year</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Pawsey Medal</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Gottschalk Medal</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Edgeworth David Medal</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">W. H. (Beattie) Steel Medal</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Archibald Liversidge Medal and Lecture</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr><tr><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Prime Minister&#x27;s Prize for Science</td><td style="text-align: left; padding: 1px 12px 1px 0; border: none; white-space: nowrap; vertical-align: top;">Award</td></tr></tbody></table><div style="color: #999; margin-top: 3px;">Showing 20 of 32 rows</div></div>


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
Graph(118 entities, 220 relationships, source='data/EOASI2022-ro-crate')
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
