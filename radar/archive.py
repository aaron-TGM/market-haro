"""Append-only archive: the price history as text, so git can hold it forever.

WHY NOT JUST COMMIT THE SQLITE FILE

Because it would eat the repo. SQLite rewrites pages all over the file on every
write, so git sees a brand-new binary blob each day and stores a full copy. At
~1,700 products a daily snapshot is ~1,700 rows; after a year the database is
tens of megabytes, and a year of daily commits of a tens-of-megabytes binary is
gigabytes of pack file against GitHub's 5 GB soft limit. Git cannot delta a
SQLite file in any useful way.

So the durable artifact is NDJSON, one file per month, one JSON object per line,
sorted deterministically. A day's run appends ~1,700 lines to the end of one
file and changes nothing else, which is a diff git stores in kilobytes. The
SQLite database becomes a derived artifact -- rebuildable at any time, and
gitignored.

  radar export     database -> data/history/YYYY-MM.ndjson   (idempotent)
  radar restore    data/history/*.ndjson -> database

WHY THIS IS THE PART THAT MATTERS

tcgapi.dev gives weekly history back to March 2025 and daily history for about a
quarter. Every day you sync, you record a daily point the API will not sell back
to you next year. The archive is that accumulation, and it is the one thing here
that cannot be recreated if it is lost. It is plain text on purpose: readable in
ten years, greppable, diffable, and not dependent on this code still running.

DETERMINISM

Lines are sorted by (obs_date, card_id, printing) and written with sorted JSON
keys and no float reformatting beyond what json does. Re-exporting an unchanged
month produces a byte-identical file, so `git status` is clean when nothing
happened -- which is what makes "commit only if changed" safe in CI.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator

# Written for every row, in this order. Anything None is omitted from the line
# entirely rather than written as null -- most rows carry only a few of these,
# and omitting them roughly halves the file.
FIELDS = (
    "card_id",
    "printing",
    "obs_date",
    "market_price",
    "low_price",
    "median_price",
    "buylist_price",
    "lowest_with_shipping",
    "total_listings",
    "sales_volume",
    "avg_sales_price",
    "source",
)

# Card metadata changes rarely, so it lives in one file rather than per month.
CARD_FIELDS = (
    "id",
    "tcgplayer_id",
    "name",
    "clean_name",
    "number",
    "rarity",
    "image_url",
    "tcgplayer_url",
    "product_type",
    "foil_only",
    "set_id",
    "set_name",
    "game_name",
)


def _line(row: dict, fields: Iterable[str]) -> str:
    return json.dumps(
        {k: row[k] for k in fields if row.get(k) is not None},
        sort_keys=True,
        separators=(",", ":"),
    )


def _read_ndjson(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    # A truncated last line from an interrupted write. Skip it;
                    # the next export rewrites the whole month anyway.
                    continue


def export(db, root: str | Path) -> dict[str, Any]:
    """Database -> NDJSON. Rewrites each month whole, so it is safe to re-run.

    Rewriting rather than appending is deliberate: a re-sync that corrects a
    price should correct the archive too, and an append-only writer would leave
    both values on disk with no way to tell which won.
    """
    root = Path(root)
    (root / "history").mkdir(parents=True, exist_ok=True)

    by_month: dict[str, list[dict]] = defaultdict(list)
    for row in db.conn.execute(
        f"SELECT {', '.join(FIELDS)} FROM price_points ORDER BY obs_date, card_id, printing"
    ):
        d = dict(row)
        by_month[str(d["obs_date"])[:7]].append(d)

    written, points = [], 0
    for month, rows in sorted(by_month.items()):
        path = root / "history" / f"{month}.ndjson"
        body = "\n".join(_line(r, FIELDS) for r in rows) + "\n"
        # Only touch the file if the bytes differ, so an unchanged month keeps
        # its mtime and stays out of the commit.
        if not path.exists() or path.read_text(encoding="utf-8") != body:
            path.write_text(body, encoding="utf-8")
            written.append(path.name)
        points += len(rows)

    cards = [dict(r) for r in db.conn.execute(
        f"SELECT {', '.join(CARD_FIELDS)} FROM cards ORDER BY id"
    )]
    cpath = root / "cards.ndjson"
    cbody = "\n".join(_line(c, CARD_FIELDS) for c in cards) + "\n"
    if not cpath.exists() or cpath.read_text(encoding="utf-8") != cbody:
        cpath.write_text(cbody, encoding="utf-8")
        written.append(cpath.name)

    return {
        "months": len(by_month),
        "points": points,
        "cards": len(cards),
        "changed": written,
        "root": str(root),
    }


def restore(db, root: str | Path, *, batch: int = 20000) -> dict[str, Any]:
    """NDJSON -> database. Idempotent; run it on an empty DB or an existing one.

    Cards are loaded first so the price rows join to something. Batched because
    a couple of years of history is a few hundred thousand rows and holding all
    of it in one list is pointless.
    """
    root = Path(root)
    cards = list(_read_ndjson(root / "cards.ndjson"))
    if cards:
        db.upsert_cards(cards)

    months = sorted((root / "history").glob("*.ndjson")) if (root / "history").exists() else []
    points = 0
    for path in months:
        buf: list[dict] = []
        for row in _read_ndjson(path):
            buf.append(row)
            if len(buf) >= batch:
                points += db.upsert_price_points(buf)
                buf = []
        if buf:
            points += db.upsert_price_points(buf)

    return {
        "months": len(months),
        "points": points,
        "cards": len(cards),
        "root": str(root),
    }
