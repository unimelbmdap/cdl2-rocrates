---
name: user-stories
description: Use when the user asks to generate user stories, research scenarios, or usage narratives from dataset collections — explores real data and writes narrative stories from a researcher's perspective
---

# User Stories

Generate narrative user stories by exploring real dataset collections. Stories capture how researchers would explore and interrogate collections, written from the researcher's perspective.

## Process

1. **Sample** — read crate metadata from the target folders. For large folders (10+ crates), sample 5-8 for variety in size and subject. For smaller folders, read all. Focus on the root Dataset entity (title, description, creator) and a scan of entity `@type` values.
2. **Profile** — for each crate, note: entity types, relationship types, scale, subject matter. Summarise what the collection contains and what discipline it serves.
3. **Imagine** — for each crate: "A researcher in a relevant discipline has come to this collection because of their existing research interests. What would they want to explore? What questions would arise?"
4. **Select** — pick the requested number (default 8). Aim for variety across disciplines, research question types, and collections. Max 2 stories per collection. At least 1 cross-collection story if multiple collections are available.
5. **Write** — produce each story as a markdown file in `design/ux/stories/` (or user-specified directory). Kebab-case filenames: `<collection>-<theme>.md`.
6. **Index** — create/update `README.md` in the output directory listing all stories with one-line summaries.

## Story Format

Each story contains:

- **Title** — the researcher's question, framed naturally
- **Context line** — collection(s) and discipline
- **Narrative (3-5 paragraphs)** — the researcher's exploration journey

## Mandatory Conventions

Stories describe the *journey of exploration*, not finished research. They capture what a researcher would *want to ask*, not what they already found.

- **Researcher questions in italics** — woven into the narrative. These are the "can I see...?" and "I wonder if...?" moments. Every story must have at least 3-4.
- **Named character with role** — "Sofia, a historian studying..." not first-person "I". Use first names only, no surnames.
- **Research-motivated** — the researcher arrives because they have a research question. They are not browsing randomly.
- **Domain vocabulary only** — say "show me everything connected to this person", never "find adjacent nodes." Say "are there natural groupings?", never "run community detection." Never use: nodes, edges, graph, degree, hub, cluster, network topology.
- **No API references or code** — stories describe intent, not implementation.
- **3-5 paragraphs, no section headers** — flowing narrative, not a structured report.

## Research Question Types

Vary stories across these types:

- **Tracing connections** — "show me everything related to this person/place/organisation"
- **Understanding scope** — "what's in this collection? What kinds of materials does it hold?"
- **Comparing across sources** — "do these two collections overlap?"
- **Following a thread through time** — "how did this change over the decades?"
- **Finding related materials across types** — "this person has records, publications, and affiliations — can I see them together?"

## Edge Cases

- **Path not found / no crates:** report the problem, ask the user to check.
- **Fewer collections than stories:** relax the max-2-per-collection limit. Note why in README.
- **Single collection:** vary research question type and discipline angle.
- **Very large crates (10,000+ entities):** read root entity and type sample only.
