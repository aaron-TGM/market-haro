"""Render one of the Markdown docs as a hosted page in the product's style.

    python scripts/build_doc.py docs/LAUNCH.md "Market Haro Launch Plan"

Writes out/<stem>.html and out/<stem>.artifact.html. Small Markdown only --
the same subset the weekly note uses, plus tables, horizontal rules, code
fences and task checkboxes -- which is all the docs here use.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"

CSS = """
:root{--bg:#07090c;--surface:#0d1117;--surface-2:#131a22;--line:#2a2418;--line-2:#3d3424;--text:#f2ead8;--muted:#9a917f;--accent:#e0a030;--up:#5fd08a;
  --mono:"JetBrains Mono",ui-monospace,Menlo,monospace;--sans:"IBM Plex Sans",-apple-system,"Segoe UI",Helvetica,Arial,sans-serif}
*{box-sizing:border-box}
html{color-scheme:dark}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.65 var(--sans)}
a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
.wrap{max-width:860px;margin:0 auto;padding:36px 24px 90px}
.brand{font:700 10.5px/1 var(--mono);letter-spacing:.22em;text-transform:uppercase;color:var(--accent);margin-bottom:14px}
h1{font:700 32px/1.15 var(--mono);letter-spacing:-.01em;margin:0 0 18px;text-wrap:balance}
h2{font:700 13px/1.3 var(--mono);letter-spacing:.16em;text-transform:uppercase;color:var(--accent);margin:40px 0 12px;padding-top:22px;border-top:1px solid var(--line)}
h3{font:700 16px/1.3 var(--mono);margin:22px 0 8px}
p{margin:0 0 14px;max-width:72ch}
blockquote{margin:14px 0;padding:12px 18px;border-left:3px solid var(--accent);background:var(--surface);max-width:72ch}
blockquote p{margin:0 0 10px} blockquote p:last-child{margin:0}
ul,ol{padding-left:24px;margin:0 0 14px;max-width:72ch} li{margin:5px 0}
li.task{list-style:none;margin-left:-24px;display:grid;grid-template-columns:22px 1fr;gap:8px}
li.task i{display:inline-block;width:15px;height:15px;border:1.5px solid var(--accent);border-radius:2px;margin-top:5px}
li.task.done i{background:var(--accent)}
code{font-family:var(--mono);font-size:.9em;background:var(--surface-2);padding:1px 6px;border-radius:2px}
pre{background:var(--surface);border:1px solid var(--line);border-radius:3px;padding:12px 14px;overflow-x:auto;font:13px/1.55 var(--mono);margin:0 0 16px}
pre code{background:transparent;padding:0;font-size:inherit}
table{border-collapse:collapse;width:100%;margin:8px 0 18px;font-size:14.5px}
th,td{border:1px solid var(--line);padding:9px 11px;text-align:left;vertical-align:top}
th{font:400 10.5px/1.3 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--muted);background:var(--surface)}
td:first-child{font-weight:600}
hr{border:0;border-top:1px solid var(--line);margin:30px 0}
.tablewrap{overflow-x:auto}
strong{color:#fff}
"""


def _inl(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\w)", r"<em>\1</em>", s)
    return s


def render(md: str) -> str:
    out: list[str] = []
    lines = md.splitlines()
    i = 0
    para: list[str] = []
    list_stack: list[str] = []

    def flush_para():
        nonlocal para
        if para:
            out.append("<p>" + _inl(" ".join(x.strip() for x in para)) + "</p>")
            para = []

    def close_lists():
        while list_stack:
            out.append(f"</{list_stack.pop()}>")

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            flush_para(); close_lists()
            j = i + 1
            buf = []
            while j < len(lines) and not lines[j].startswith("```"):
                buf.append(lines[j]); j += 1
            out.append("<pre><code>" + html.escape("\n".join(buf)) + "</code></pre>")
            i = j + 1
            continue
        if line.startswith("|"):
            flush_para(); close_lists()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"^\|\s*-{2,}", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], rows[1:]
            out.append('<div class="tablewrap"><table><thead><tr>' + "".join(f"<th>{_inl(c)}</th>" for c in head)
                       + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{_inl(c)}</td>" for c in r) + "</tr>" for r in body)
                       + "</tbody></table></div>")
            continue
        if line.startswith(">"):
            flush_para(); close_lists()
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i][1:].strip()); i += 1
            paras = [p for p in "\n".join(buf).split("\n\n")]
            out.append("<blockquote>" + "".join(f"<p>{_inl(p.replace(chr(10), ' '))}</p>" for p in paras if p.strip()) + "</blockquote>")
            continue
        if line.strip() == "---":
            flush_para(); close_lists(); out.append("<hr>"); i += 1; continue
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            flush_para(); close_lists()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_inl(m.group(2))}</h{lvl}>")
            i += 1; continue
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if m:
            flush_para()
            kind = "ol" if m.group(2)[0].isdigit() else "ul"
            if not list_stack or list_stack[-1] != kind:
                close_lists(); out.append(f"<{kind}>"); list_stack.append(kind)
            text = m.group(3)
            t = re.match(r"^\[( |x)\]\s+(.*)$", text)
            if t:
                out.append(f'<li class="task{" done" if t.group(1) == "x" else ""}"><i></i><span>{_inl(t.group(2))}</span></li>')
            else:
                out.append(f"<li>{_inl(text)}</li>")
            i += 1; continue
        if not line.strip():
            flush_para(); close_lists(); i += 1; continue
        para.append(line); i += 1
    flush_para(); close_lists()
    return "\n".join(out)


def build(md_path: Path, title: str) -> tuple[str, str]:
    md = md_path.read_text(encoding="utf-8")
    # the first H1 in the file is the page's heading; the <title> is the given name
    body_html = render(md)
    body = f"""<title>{html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=IBM+Plex+Sans:wght@400;600&display=swap">
<style>{CSS}</style>
<div class="wrap"><div class="brand">Market Haro · from GUNDECK.AI</div>
{body_html}
</div>
"""
    head_end = body.index("</style>") + len("</style>")
    full = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">' + body[:head_end]
            + "</head><body>" + body[head_end:] + "</body></html>")
    return body, full


if __name__ == "__main__":
    src = Path(sys.argv[1])
    title = sys.argv[2] if len(sys.argv) > 2 else src.stem
    body, full = build(src, title)
    stem = src.stem.lower()
    (OUT / f"{stem}.artifact.html").write_text(body, encoding="utf-8")
    (OUT / f"{stem}.html").write_text(full, encoding="utf-8")
    print(f"out/{stem}.html {len(full):,} bytes")
