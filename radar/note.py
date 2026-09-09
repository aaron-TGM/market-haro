"""The weekly note: a few hundred words in a person's voice.

A pure data product feels cold, and the thing subscribers
actually forward to each other is a paragraph with a point of view. So the
page and the email carry a slot for one -- written by a person, not
generated, and shown only while it is fresh.

Drop a file at data/notes/YYYY-MM-DD.md. The newest note dated within
MAX_AGE_DAYS of the issue is rendered at the top of the page under
"This week" and at the top of the digest email. Older notes stay in the
folder as a record and are not shown. No file, no slot -- the page does
not nag for one.

Markdown support is deliberately small: paragraphs, **bold**, *italic*,
[links](https://...), `##` headings and `-` lists. Enough for a note, not
enough to break the page.
"""

from __future__ import annotations

import html
import re
from datetime import date as _date
from pathlib import Path

MAX_AGE_DAYS = 10
_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")


def latest(root: Path, today: str, *, max_age_days: int = MAX_AGE_DAYS) -> dict | None:
    folder = Path(root) / "notes"
    if not folder.exists():
        return None
    try:
        t = _date.fromisoformat(today)
    except (ValueError, TypeError):
        return None
    best = None
    for p in folder.glob("*.md"):
        m = _DATE.match(p.name)
        if not m:
            continue
        d = m.group(1)
        try:
            age = (t - _date.fromisoformat(d)).days
        except ValueError:
            continue
        if age < 0 or age > max_age_days:
            continue
        if best is None or d > best[0]:
            best = (d, p)
    if not best:
        return None
    text = best[1].read_text(encoding="utf-8").strip()
    return {"date": best[0], "markdown": text, "html": to_html(text)}


def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\w)", r"<em>\1</em>", s)
    return s


def to_html(md: str) -> str:
    out: list[str] = []
    para: list[str] = []
    in_list = False

    def flush():
        nonlocal para
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para = []

    for line in md.splitlines():
        line = line.rstrip()
        if not line.strip():
            flush()
            if in_list:
                out.append("</ul>"); in_list = False
            continue
        if line.startswith("- ") or line.startswith("* "):
            flush()
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append("<li>" + _inline(line[2:]) + "</li>")
            continue
        if in_list:
            out.append("</ul>"); in_list = False
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            flush()
            out.append(f"<h{len(m.group(1)) + 2}>{_inline(m.group(2))}</h{len(m.group(1)) + 2}>")
            continue
        para.append(line.strip())
    flush()
    if in_list:
        out.append("</ul>")
    return "\n".join(out)
