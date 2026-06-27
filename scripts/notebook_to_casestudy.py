"""Convert a verified stepwise notebook into a curated case-study Markdown page.

Matches the house style of the existing case studies (docs/case-studies/*.md):
code in fenced ```python blocks, text outputs in fenced blocks, small HTML tables
(Records / DataFrames) inline, and plotly / sigma figures rendered to docs/assets/
and embedded via <iframe>. Image attachments (e.g. a Gephi screenshot) are written
out as PNGs and referenced with a normal Markdown image.

The notebook's own Markdown cells (title, intro, "What you'll learn", numbered
sections, "Next steps") pass through unchanged, so prepare those in the notebook first.

The generated <iframe> paths (`../../assets/...`) assume the page is published by
MkDocs under docs/case-studies/ with directory URLs (so the rendered page lives at
case-studies/<slug>/index.html). Output elsewhere would need different relative paths.

Usage (from repo root):
    uv run --with plotly scripts/notebook_to_casestudy.py \\
        docs/tutorials/draft/EOAS_women_casestudy-stepwise.ipynb \\
        docs/case-studies/women-in-the-encyclopedia-of-australian-science.md \\
        eoas-women --draft --provenance-file scratchpad/prov.txt

`--draft` inserts a "Draft case study" admonition before the first `##` heading.
`--provenance-file` prepends an HTML comment (data path / run date / regenerate note).
"""

from __future__ import annotations

import argparse
import base64
import json
import re
from pathlib import Path

import plotly.io as pio

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSETS = ROOT / "docs" / "assets"

DRAFT_ADMONITION = (
    '!!! note "Draft case study"\n\n'
    "    This case study is an early draft. The analysis is sound and the outputs are real,\n"
    "    but upcoming refinements will further improve the code and language clarity.\n"
)

INLINE_HTML_LIMIT = 50_000  # non-table HTML bigger than this is externalised to an asset
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
# structural markers from crategraph's sigma renderer template
NETWORK_MARKERS = (
    "sigma-container",
    "window.sigmaconfig",
    "graphdatapacked",
    "force-graph",
    "3d-force-graph",
)
TABLE_MARKERS = ("<table", 'class="dataframe"', "records:")


def _join(value) -> str:
    if value is None:
        return ""
    return "".join(value) if isinstance(value, list) else str(value)


def _fence(text: str) -> str:
    """Backtick fence long enough to survive any backtick run inside `text`."""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def _code_block(src: str, lang: str = "python") -> str:
    src = src.rstrip()
    f = _fence(src)
    return f"{f}{lang}\n{src}\n{f}\n"


def _text_output(text: str) -> str:
    """Fence plain text output, stripping ANSI; return "" for empty output."""
    text = ANSI_RE.sub("", _join(text)).rstrip()
    if not text:
        return ""
    f = _fence(text)
    return f"{f}\n{text}\n{f}\n"


def _is_table_html(html: str) -> bool:
    low = html.lower()
    return any(m in low for m in TABLE_MARKERS)


def _is_network_html(html: str) -> bool:
    low = html.lower()
    return any(m in low for m in NETWORK_MARKERS)


def _write_plotly_asset(fig_json: dict, path: Path) -> int:
    fig = pio.from_json(json.dumps(fig_json))
    pio.write_html(
        fig, str(path), include_plotlyjs="cdn", full_html=True, config={"displayModeBar": False}
    )
    return int(fig.layout.height or 450)


def convert(
    nb_path: Path, out_path: Path, prefix: str, assets_dir: Path, provenance: str, draft: bool
) -> int:
    nb = json.loads(nb_path.read_text())
    assets_dir.mkdir(parents=True, exist_ok=True)
    out: list[str] = []
    fig_n = 0

    def asset(ext: str) -> tuple[Path, str]:
        nonlocal fig_n
        fig_n += 1
        return assets_dir / f"{prefix}-{fig_n}.{ext}", f"{prefix}-{fig_n}.{ext}"

    def iframe(name: str, height: int, title: str) -> str:
        return (
            f'<iframe src="../../assets/{name}" width="100%" height="{height}"\n'
            f'        style="border:none" loading="lazy" title="{title}"></iframe>\n'
        )

    for cell in nb["cells"]:
        src = "".join(cell["source"])

        if cell["cell_type"] == "markdown":
            for att_name, att in (cell.get("attachments") or {}).items():
                for mime, b64 in att.items():
                    path, name = asset(mime.split("/")[-1])
                    path.write_bytes(base64.b64decode(b64))
                    # rewrite only this attachment's own (attachment:..) / (<attachment:..>) ref
                    ref = re.compile(r"!\[[^\]]*\]\(<?attachment:" + re.escape(att_name) + r">?\)")
                    src = ref.sub(f"![{att_name}](../assets/{name})", src)
            out.append(src.rstrip() + "\n")
            continue

        out.append(_code_block(src))
        for o in cell.get("outputs", []):
            kind = o.get("output_type")
            if kind == "stream":
                out.append(_text_output(o.get("text", "")))
                continue
            if kind == "error":
                tb = "\n".join(o.get("traceback", []))
                out.append(_text_output(tb or f"{o.get('ename', '')}: {o.get('evalue', '')}"))
                continue
            data = o.get("data", {})
            if "application/vnd.plotly.v1+json" in data:
                path, name = asset("html")
                height = _write_plotly_asset(data["application/vnd.plotly.v1+json"], path)
                out.append(iframe(name, height + 20, "figure"))
            elif "text/html" in data:
                html = _join(data["text/html"])
                if _is_table_html(html):
                    # wrap in a scroll container so wide tables don't overflow the page
                    out.append('<div class="nb-table">\n' + html.rstrip() + "\n</div>\n")
                elif _is_network_html(html) or len(html) > INLINE_HTML_LIMIT:
                    path, name = asset("html")
                    path.write_text(html)
                    out.append(iframe(name, 600, "network"))
                elif "text/plain" in data:
                    out.append(_text_output(_join(data["text/plain"])))  # prefer plain text
                else:
                    out.append(html.rstrip() + "\n")  # small unknown HTML: inline as-is
            elif "image/png" in data:
                path, name = asset("png")
                path.write_bytes(base64.b64decode(_join(data["image/png"])))
                out.append(f"![figure](../assets/{name})\n")
            elif "text/plain" in data:
                out.append(_text_output(_join(data["text/plain"])))
        out.append("")

    body = "\n".join(out)
    if draft:
        m = re.search(r"(?m)^## ", body)
        if m:
            body = body[: m.start()] + DRAFT_ADMONITION + "\n" + body[m.start() :]
    head = (provenance.rstrip() + "\n\n") if provenance else ""
    out_path.write_text(head + body.lstrip("\n"))
    return fig_n


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("notebook", type=Path)
    parser.add_argument("out_md", type=Path)
    parser.add_argument(
        "asset_prefix", help="e.g. eoas-women; assets become docs/assets/<prefix>-N.*"
    )
    parser.add_argument("--assets-dir", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument(
        "--provenance-file",
        type=Path,
        default=None,
        help="HTML comment prepended verbatim (data path / run date / regenerate note)",
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="insert a 'Draft case study' admonition before the first heading",
    )
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.asset_prefix):
        parser.error("asset_prefix must contain only letters, numbers, hyphens, underscores")

    provenance = args.provenance_file.read_text() if args.provenance_file else ""
    n = convert(
        args.notebook, args.out_md, args.asset_prefix, args.assets_dir, provenance, args.draft
    )
    print(f"wrote {args.out_md}  ({n} figures -> {args.assets_dir})")


if __name__ == "__main__":
    main()
