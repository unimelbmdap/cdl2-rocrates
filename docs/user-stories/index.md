# User Stories

Narrative stories capturing how researchers might explore and interrogate RO-Crate collections. Each story is written from a researcher's perspective, grounded in real collection data, and designed to surface the kinds of questions researchers naturally ask.

These stories are intended for API fitness evaluation — reading each story, identifying the researcher's questions (in italics), and mapping them to crategraph API calls to find gaps and friction.

!!! note "These stories are fictional"
    The researchers, their names, and their specific research projects are invented. The collections, entities, and relationships referenced in each story are real — drawn from OHRM and LDaCA RO-Crate datasets — but the scenarios are imagined to illustrate plausible research workflows.

## Stories

| Story | Collection | Discipline | Research Question Type |
|-------|-----------|------------|----------------------|
| [Who walked together, and what else did they share?][wall] | WALL (Wallaby Club) | Social history | Tracing connections |
| [How did the way colonists wrote change?][cooee] | COOEE (Oz Early English) | Historical linguistics | Temporal thread |
| [How did children move through Victoria's care system?][wami] | WAMI (Pathways) | Welfare history | Related materials across types |
| [What did Holmer actually record, and where do the gaps start?][holmer] | Holmer Fieldnotes | Language documentation | Understanding scope |
| [How did Arrowsmith's map grow as the colony took shape?][asmp] | ASMP (Arrowsmith Maps) | Cartographic history | Temporal thread |
| [What trail did Joseph Needham leave across institutions and archives?][whso] | WHSO (World History of Science) | History of science | Tracing connections |
| [What does Australian English look like across two centuries?][sydney] | Sydney Speaks + COOEE | Sociolinguistics | Comparing across sources |
| [Which architecture firms shaped multiple university campuses?][bmau] | BMAU (Building Modern Aus Unis) | Architectural history | Tracing connections |

[wall]: https://github.com/unimelbmdap/cdl2-rocrates/blob/main/design/ux/stories/wall-club-membership-ties.md
[cooee]: https://github.com/unimelbmdap/cdl2-rocrates/blob/main/design/ux/stories/cooee-colonial-english-change.md
[wami]: https://github.com/unimelbmdap/cdl2-rocrates/blob/main/design/ux/stories/wami-care-institutions.md
[holmer]: https://github.com/unimelbmdap/cdl2-rocrates/blob/main/design/ux/stories/holmer-indigenous-language-scope.md
[asmp]: https://github.com/unimelbmdap/cdl2-rocrates/blob/main/design/ux/stories/asmp-map-evolution.md
[whso]: https://github.com/unimelbmdap/cdl2-rocrates/blob/main/design/ux/stories/whso-scientific-career.md
[sydney]: https://github.com/unimelbmdap/cdl2-rocrates/blob/main/design/ux/stories/sydney-cooee-australian-english-arc.md
[bmau]: https://github.com/unimelbmdap/cdl2-rocrates/blob/main/design/ux/stories/bmau-campus-design.md

## Walkthroughs

Notebook walkthroughs that follow a user story end-to-end using the crategraph API, showing what works well and where the API has gaps.

- [**The Wallaby Club**](walkthrough-wall-club.ipynb) — follows the WALL story through membership, leadership, family ties, temporal overlaps, and the walks themselves
