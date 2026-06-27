"""Recover a source notebook (code + prose, no outputs) from a curated case-study page.

The reverse of scripts/notebook_to_casestudy.py, for the case where someone edited a
published docs/case-studies/*.md directly and wants those code/prose edits back in a
notebook. Outputs are NOT recovered (figures, tables, text outputs are dropped) -- run
the notebook to regenerate them. The draft admonition and provenance comment are dropped
too. Consecutive Markdown in the page becomes one Markdown cell (cell boundaries from the
original notebook are not preserved).

What it keeps:    ```python blocks -> code cells; everything else -> Markdown cells,
                  including prose-level ```bash etc. fenced blocks.
What it drops:    bare ``` output blocks, <iframe>/<table>/<div>/<pre> output HTML,
                  ![](../assets/...) figures, the !!! note draft box, the leading <!-- -->.

Usage (from repo root):
    uv run scripts/casestudy_to_notebook.py \\
        docs/case-studies/women-in-the-encyclopedia-of-australian-science.md \\
        docs/tutorials/draft/recovered.ipynb
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FENCE_OPEN = re.compile(r"^(`{3,})(\w*)\s*$")
HTML_OUTPUT_TAGS = ("iframe", "table", "div", "pre")


def _markdown_cell(lines: list[str]) -> dict | None:
    text = "\n".join(lines).strip("\n")
    if not text.strip():
        return None
    return {"cell_type": "markdown", "metadata": {}, "source": _as_source(text)}


def _code_cell(lines: list[str]) -> dict:
    text = "\n".join(lines).strip("\n")
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": _as_source(text),
    }


def _as_source(text: str) -> list[str]:
    lines = text.split("\n")
    return [ln + "\n" for ln in lines[:-1]] + [lines[-1]]


def _close_fence(ticks: str) -> re.Pattern:
    return re.compile(r"^" + ticks + r"\s*$")


def parse(md: str) -> list[dict]:
    # drop a leading provenance HTML comment
    md = re.sub(r"\A\s*<!--.*?-->\s*", "", md, count=1, flags=re.DOTALL)
    lines = md.split("\n")
    cells: list[dict] = []
    prose: list[str] = []
    i, n = 0, len(lines)

    def flush_prose() -> None:
        cell = _markdown_cell(prose)
        if cell:
            cells.append(cell)
        prose.clear()

    while i < n:
        line = lines[i]
        fence = FENCE_OPEN.match(line)

        if fence and fence.group(2) == "python":  # code cell
            flush_prose()
            close = _close_fence(fence.group(1))
            i += 1
            body: list[str] = []
            while i < n and not close.match(lines[i]):
                body.append(lines[i])
                i += 1
            cells.append(_code_cell(body))
            i += 1  # past the closing fence
            continue

        if fence and fence.group(2) == "":  # bare ``` -> output, drop
            close = _close_fence(fence.group(1))
            i += 1
            while i < n and not close.match(lines[i]):
                i += 1
            i += 1
            continue

        if fence:  # ```bash etc. -> keep whole, as prose
            close = _close_fence(fence.group(1))
            prose.append(line)
            i += 1
            while i < n and not close.match(lines[i]):
                prose.append(lines[i])
                i += 1
            if i < n:
                prose.append(lines[i])  # closing fence
                i += 1
            continue

        stripped = line.lstrip()
        tag = re.match(r"<(\w+)", stripped)
        if tag and tag.group(1).lower() in HTML_OUTPUT_TAGS:  # output HTML, drop block
            closer = re.compile(r"</" + tag.group(1) + r">", re.IGNORECASE)
            while i < n and not closer.search(lines[i]):
                i += 1
            i += 1  # past the line with the closing tag
            continue

        if re.match(r"!\[[^\]]*\]\(\.\./assets/", stripped):  # asset figure, drop
            i += 1
            continue

        if stripped.startswith("!!! "):  # admonition: drop it + indented body
            i += 1
            while i < n and (not lines[i].strip() or lines[i].startswith("    ")):
                i += 1
            continue

        prose.append(line)
        i += 1

    flush_prose()
    return cells


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("md", type=Path)
    parser.add_argument("out_ipynb", type=Path)
    args = parser.parse_args()

    cells = parse(args.md.read_text())
    nb = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    args.out_ipynb.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n")
    n_code = sum(c["cell_type"] == "code" for c in cells)
    print(f"wrote {args.out_ipynb}  ({len(cells)} cells, {n_code} code)")


if __name__ == "__main__":
    main()
