"""SQLite storage. One file, no server, trivially backed up.

The price history you accumulate here is the real asset -- the API only gives
weekly history back to March 2025, but every daily sync you run adds a point the
API can't give you later. Back up data/radar.sqlite3.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sets (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    slug          TEXT,
    abbreviation  TEXT,
    release_date  TEXT,
    card_count    INTEGER,
    game_name     TEXT,
    game_slug     TEXT,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cards (
    id             TEXT PRIMARY KEY,
    tcgplayer_id   INTEGER,
    name           TEXT NOT NULL,
    clean_name     TEXT,
    number         TEXT,
    rarity         TEXT,
    image_url      TEXT,
    tcgplayer_url  TEXT,
    product_type   TEXT,
    foil_only      INTEGER,
    set_id         TEXT,
    set_name       TEXT,
    game_name      TEXT,
    first_seen     TEXT NOT NULL,
    last_seen      TEXT NOT NULL,
    raw            TEXT
);
CREATE INDEX IF NOT EXISTS idx_cards_set ON cards(set_id);
CREATE INDEX IF NOT EXISTS idx_cards_tcgplayer ON cards(tcgplayer_id);

-- One row per (card, printing, observation date).
-- source: 'snapshot' = live daily pull, 'history' = backfilled weekly point.
-- Snapshots win over history for the same date.
CREATE TABLE IF NOT EXISTS price_points (
    card_id              TEXT NOT NULL,
    printing             TEXT NOT NULL DEFAULT 'Normal',
    obs_date             TEXT NOT NULL,
    market_price         REAL,
    low_price            REAL,
    median_price         REAL,
    buylist_price        REAL,
    lowest_with_shipping REAL,
    total_listings       INTEGER,
    sales_volume         INTEGER,
    avg_sales_price      REAL,
    change_24h           REAL,
    change_7d            REAL,
    change_30d           REAL,
    source               TEXT NOT NULL DEFAULT 'snapshot',
    ingested_at          TEXT NOT NULL,
    PRIMARY KEY (card_id, printing, obs_date)
);
CREATE INDEX IF NOT EXISTS idx_pp_card_date ON price_points(card_id, obs_date);
CREATE INDEX IF NOT EXISTS idx_pp_date ON price_points(obs_date);

-- Live listing floors from /cards/:id/prices/conditions. Kept as a time series
-- because watching `copies` fall is the whole point -- a card going 40 -> 12 -> 4
-- copies over three days is supply drying up in front of you.
CREATE TABLE IF NOT EXISTS floors (
    card_id     TEXT NOT NULL,
    printing    TEXT NOT NULL DEFAULT 'Normal',
    obs_ts      TEXT NOT NULL,
    condition   TEXT,
    floor_low   REAL,
    floor_ship  REAL,
    shelf_med   REAL,
    language    TEXT,
    copies      INTEGER,
    conditions  TEXT,
    PRIMARY KEY (card_id, printing, obs_ts)
);
CREATE INDEX IF NOT EXISTS idx_floors_card ON floors(card_id, printing, obs_ts DESC);

CREATE TABLE IF NOT EXISTS runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at     TEXT NOT NULL,
    finished_at    TEXT,
    requests_used  INTEGER,
    sets_seen      INTEGER,
    cards_seen     INTEGER,
    prices_written INTEGER,
    status         TEXT,
    note           TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER,
    obs_date     TEXT NOT NULL,
    card_id      TEXT NOT NULL,
    printing     TEXT NOT NULL,
    score        REAL NOT NULL,
    signals      TEXT NOT NULL,
    market_price REAL,
    change_24h   REAL,
    change_7d    REAL,
    change_30d   REAL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_date ON alerts(obs_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_unique
    ON alerts(obs_date, card_id, printing);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today() -> str:
    return date.today().isoformat()


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Add columns that CREATE TABLE IF NOT EXISTS will not add to an old file."""
        have = {r["name"] for r in self.conn.execute("PRAGMA table_info(floors)")}
        for col, typ in (("shelf_med", "REAL"), ("language", "TEXT")):
            if col not in have:
                self.conn.execute(f"ALTER TABLE floors ADD COLUMN {col} {typ}")

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # -- writes -----------------------------------------------------------------
    def upsert_sets(self, sets: Iterable[dict], game_slug: str) -> int:
        now = utcnow()
        rows = [
            (
                str(s.get("id")),
                s.get("name") or "",
                s.get("slug"),
                s.get("abbreviation"),
                s.get("release_date"),
                s.get("card_count"),
                s.get("game_name"),
                s.get("game_slug") or game_slug,
                now,
            )
            for s in sets
            if s.get("id") is not None
        ]
        with self.tx() as c:
            c.executemany(
                """INSERT INTO sets
                   (id,name,slug,abbreviation,release_date,card_count,game_name,game_slug,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name, slug=excluded.slug,
                     abbreviation=excluded.abbreviation,
                     release_date=excluded.release_date,
                     card_count=excluded.card_count,
                     game_name=excluded.game_name, game_slug=excluded.game_slug,
                     updated_at=excluded.updated_at""",
                rows,
            )
        return len(rows)

    def upsert_cards(self, cards: Iterable[dict]) -> int:
        now = utcnow()
        rows = []
        for c in cards:
            cid = c.get("id")
            if cid is None:
                continue
            rows.append(
                (
                    str(cid),
                    _int_or_none(c.get("tcgplayer_id")),
                    c.get("name") or "",
                    c.get("clean_name"),
                    str(c.get("number")) if c.get("number") is not None else None,
                    c.get("rarity"),
                    c.get("image_url"),
                    c.get("tcgplayer_url"),
                    c.get("product_type"),
                    1 if c.get("foil_only") else 0,
                    str(c.get("set_id")) if c.get("set_id") is not None else None,
                    c.get("set_name"),
                    c.get("game_name"),
                    now,
                    now,
                    json.dumps(c, separators=(",", ":"))[:20000],
                )
            )
        with self.tx() as conn:
            conn.executemany(
                """INSERT INTO cards
                   (id,tcgplayer_id,name,clean_name,number,rarity,image_url,
                    tcgplayer_url,product_type,foil_only,set_id,set_name,game_name,
                    first_seen,last_seen,raw)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   -- COALESCE on every optional field: the same card arrives from
                   -- /sets/:id/cards (has rarity, listings) and /sets/:id/prices
                   -- (has price change fields but no rarity). Whichever lands
                   -- second must not blank out what the other one knew.
                   ON CONFLICT(id) DO UPDATE SET
                     tcgplayer_id=COALESCE(excluded.tcgplayer_id, cards.tcgplayer_id),
                     name=COALESCE(NULLIF(excluded.name,''), cards.name),
                     clean_name=COALESCE(excluded.clean_name, cards.clean_name),
                     number=COALESCE(excluded.number, cards.number),
                     rarity=COALESCE(excluded.rarity, cards.rarity),
                     image_url=COALESCE(excluded.image_url, cards.image_url),
                     tcgplayer_url=COALESCE(excluded.tcgplayer_url, cards.tcgplayer_url),
                     product_type=COALESCE(excluded.product_type, cards.product_type),
                     foil_only=COALESCE(excluded.foil_only, cards.foil_only),
                     set_id=COALESCE(excluded.set_id, cards.set_id),
                     set_name=COALESCE(excluded.set_name, cards.set_name),
                     game_name=COALESCE(excluded.game_name, cards.game_name),
                     last_seen=excluded.last_seen,
                     raw=excluded.raw""",
                rows,
            )
        return len(rows)

    def upsert_price_points(self, points: Iterable[dict]) -> int:
        """points: dicts with card_id, printing, obs_date, source + price fields."""
        now = utcnow()
        rows = []
        for p in points:
            if p.get("card_id") is None or not p.get("obs_date"):
                continue
            rows.append(
                (
                    str(p["card_id"]),
                    p.get("printing") or "Normal",
                    p["obs_date"],
                    _float_or_none(p.get("market_price")),
                    _float_or_none(p.get("low_price")),
                    _float_or_none(p.get("median_price")),
                    _float_or_none(p.get("buylist_price")),
                    _float_or_none(p.get("lowest_with_shipping")),
                    _int_or_none(p.get("total_listings")),
                    _int_or_none(p.get("sales_volume")),
                    _float_or_none(p.get("avg_sales_price")),
                    _float_or_none(p.get("change_24h")),
                    _float_or_none(p.get("change_7d")),
                    _float_or_none(p.get("change_30d")),
                    p.get("source") or "snapshot",
                    now,
                )
            )
        with self.tx() as conn:
            # A live snapshot always beats a backfilled history point for a date;
            # a history point never overwrites a snapshot.
            conn.executemany(
                """INSERT INTO price_points
                   (card_id,printing,obs_date,market_price,low_price,median_price,
                    buylist_price,lowest_with_shipping,total_listings,
                    sales_volume,avg_sales_price,
                    change_24h,change_7d,change_30d,source,ingested_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(card_id,printing,obs_date) DO UPDATE SET
                     market_price=CASE WHEN excluded.source='snapshot'
                        OR price_points.source<>'snapshot'
                        THEN COALESCE(excluded.market_price, price_points.market_price)
                        ELSE price_points.market_price END,
                     low_price=COALESCE(excluded.low_price, price_points.low_price),
                     median_price=COALESCE(excluded.median_price, price_points.median_price),
                     buylist_price=COALESCE(excluded.buylist_price, price_points.buylist_price),
                     lowest_with_shipping=COALESCE(excluded.lowest_with_shipping,
                                                   price_points.lowest_with_shipping),
                     total_listings=COALESCE(excluded.total_listings, price_points.total_listings),
                     sales_volume=COALESCE(excluded.sales_volume, price_points.sales_volume),
                     avg_sales_price=COALESCE(excluded.avg_sales_price, price_points.avg_sales_price),
                     change_24h=COALESCE(excluded.change_24h, price_points.change_24h),
                     change_7d=COALESCE(excluded.change_7d, price_points.change_7d),
                     change_30d=COALESCE(excluded.change_30d, price_points.change_30d),
                     source=CASE WHEN excluded.source='snapshot' THEN 'snapshot'
                                 ELSE price_points.source END,
                     ingested_at=excluded.ingested_at""",
                rows,
            )
        return len(rows)

    def save_floors(self, floors: Iterable[dict]) -> int:
        now = utcnow()
        rows = [
            (
                str(f["card_id"]),
                f.get("printing") or "Normal",
                now,
                f.get("condition"),
                _float_or_none(f.get("floor_low")),
                _float_or_none(f.get("floor_ship")),
                _float_or_none(f.get("shelf_med")),
                f.get("language"),
                _int_or_none(f.get("copies")),
                json.dumps(f.get("conditions") or [], separators=(",", ":")),
            )
            for f in floors
        ]
        with self.tx() as c:
            c.executemany(
                """INSERT INTO floors
                   (card_id,printing,obs_ts,condition,floor_low,floor_ship,shelf_med,language,
                    copies,conditions)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(card_id,printing,obs_ts) DO UPDATE SET
                     floor_low=excluded.floor_low, floor_ship=excluded.floor_ship,
                     shelf_med=excluded.shelf_med, language=excluded.language,
                     copies=excluded.copies, conditions=excluded.conditions""",
                rows,
            )
        return len(rows)

    def latest_floors(self) -> dict[tuple[str, str], dict]:
        """Most recent floor reading per (card, printing), plus the previous copy count."""
        out: dict[tuple[str, str], dict] = {}
        for row in self.conn.execute(
            """SELECT f.* FROM floors f
               JOIN (SELECT card_id, printing, MAX(obs_ts) AS m FROM floors
                     GROUP BY card_id, printing) t
                 ON t.card_id=f.card_id AND t.printing=f.printing AND t.m=f.obs_ts"""
        ):
            out[(row["card_id"], row["printing"])] = {k: row[k] for k in row.keys()}
        # How many copies were on the shelf last time we looked?
        for row in self.conn.execute(
            """SELECT card_id, printing, copies, obs_ts FROM floors
               ORDER BY card_id, printing, obs_ts DESC"""
        ):
            key = (row["card_id"], row["printing"])
            cur = out.get(key)
            if cur and row["obs_ts"] < cur["obs_ts"] and "prev_copies" not in cur:
                cur["prev_copies"] = row["copies"]
                cur["prev_ts"] = row["obs_ts"]
        return out

    def start_run(self, note: str = "") -> int:
        with self.tx() as c:
            cur = c.execute(
                "INSERT INTO runs (started_at, status, note) VALUES (?,?,?)",
                (utcnow(), "running", note),
            )
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, **fields: Any) -> None:
        allowed = {
            "requests_used",
            "sets_seen",
            "cards_seen",
            "prices_written",
            "status",
            "note",
        }
        sets_sql = ", ".join(f"{k}=?" for k in fields if k in allowed)
        values = [fields[k] for k in fields if k in allowed]
        sql = "UPDATE runs SET finished_at=?" + (f", {sets_sql}" if sets_sql else "")
        sql += " WHERE id=?"
        with self.tx() as c:
            c.execute(sql, [utcnow(), *values, run_id])

    def record_alerts(self, run_id: int, obs_date: str, alerts: Iterable[dict]) -> int:
        now = utcnow()
        rows = [
            (
                run_id,
                obs_date,
                a["card_id"],
                a.get("printing") or "Normal",
                a["score"],
                json.dumps(a.get("signals") or []),
                a.get("market_price"),
                a.get("change_24h"),
                a.get("change_7d"),
                a.get("change_30d"),
                now,
            )
            for a in alerts
        ]
        with self.tx() as c:
            c.executemany(
                """INSERT INTO alerts
                   (run_id,obs_date,card_id,printing,score,signals,market_price,
                    change_24h,change_7d,change_30d,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(obs_date,card_id,printing) DO UPDATE SET
                     run_id=excluded.run_id, score=excluded.score,
                     signals=excluded.signals, market_price=excluded.market_price,
                     change_24h=excluded.change_24h, change_7d=excluded.change_7d,
                     change_30d=excluded.change_30d""",
                rows,
            )
        return len(rows)

    # -- reads ------------------------------------------------------------------
    # A date represented by a handful of rows is not an observation date. Since
    # snapshots are dated by the API's `last_updated_at` rather than by the fetch,
    # a few brand-new products with no price at all can carry a date a day or two
    # ahead of the real batch -- and that date would otherwise become the header
    # of the dashboard and the basis of `latest_prices`.
    MIN_ROWS_FOR_OBS_DATE = 25

    def latest_obs_date(self) -> str | None:
        """Most recent snapshot date with enough priced rows to mean something."""
        row = self.conn.execute(
            """SELECT obs_date FROM price_points
               WHERE source='snapshot' AND market_price IS NOT NULL
               GROUP BY obs_date
               HAVING COUNT(*) >= ?
               ORDER BY obs_date DESC LIMIT 1""",
            (self.MIN_ROWS_FOR_OBS_DATE,),
        ).fetchone()
        if row:
            return row["obs_date"]
        # Nothing clears the bar (a brand-new database) -- fall back to the max.
        row = self.conn.execute(
            "SELECT MAX(obs_date) AS d FROM price_points WHERE source='snapshot'"
        ).fetchone()
        return row["d"] if row and row["d"] else None

    def latest_prices(self, obs_date: str | None = None, *, lookback_days: int = 7) -> list[sqlite3.Row]:
        """The most recent snapshot row for each (card, printing), not one date.

        Rows are dated by the API's `last_updated_at`, and the batch does not
        refresh every product on the same day -- pulled 2026-08-12 it carried
        1,142 rows stamped 08-10 and 873 stamped 08-11. Filtering on a single
        date would have silently dropped 56% of the game from the screen, which
        is a much worse failure than showing a price that is one day older.

        `lookback_days` bounds how stale a row may be and still count as current.
        Anything older than that is a product that has stopped being repriced,
        and its own history is the honest place to read it.
        """
        obs_date = obs_date or self.latest_obs_date()
        if not obs_date:
            return []
        cutoff = (date.fromisoformat(obs_date) - timedelta(days=lookback_days)).isoformat()
        return self.conn.execute(
            """SELECT p.*, c.name, c.number, c.rarity, c.set_name, c.image_url,
                      c.tcgplayer_id, c.tcgplayer_url, c.product_type
               FROM price_points p
               JOIN cards c ON c.id = p.card_id
               JOIN (
                   SELECT card_id, printing, MAX(obs_date) AS d
                   FROM price_points
                   WHERE source='snapshot' AND obs_date BETWEEN ? AND ?
                   GROUP BY card_id, printing
               ) latest
                 ON latest.card_id = p.card_id
                AND latest.printing = p.printing
                AND latest.d = p.obs_date
               WHERE p.source='snapshot'
               ORDER BY p.market_price DESC""",
            (cutoff, obs_date),
        ).fetchall()

    def series(self, card_id: str, printing: str, limit: int = 400) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT obs_date, market_price FROM price_points
               WHERE card_id=? AND printing=? AND market_price IS NOT NULL
               ORDER BY obs_date ASC LIMIT ?""",
            (card_id, printing, limit),
        ).fetchall()

    def all_series(self) -> dict[tuple[str, str], list[tuple[str, float]]]:
        """Every price series in one pass -- far faster than per-card queries."""
        out: dict[tuple[str, str], list[tuple[str, float]]] = {}
        for row in self.conn.execute(
            """SELECT card_id, printing, obs_date, market_price FROM price_points
               WHERE market_price IS NOT NULL
               ORDER BY card_id, printing, obs_date ASC"""
        ):
            out.setdefault((row["card_id"], row["printing"]), []).append(
                (row["obs_date"], float(row["market_price"]))
            )
        return out

    def all_series_with_volume(
        self,
    ) -> dict[tuple[str, str], list[tuple[str, float, float, float | None]]]:
        """Every price series with its daily sales volume and realised sale price.

        Four columns, not three: `market_price` is derived from listings, while
        `avg_sales_price` is what copies actually changed hands for that day.
        The gap between them is the settled-price measurement in invest.py.
        """
        out: dict[tuple[str, str], list[tuple[str, float, float, float | None]]] = {}
        for row in self.conn.execute(
            """SELECT card_id, printing, obs_date, market_price, sales_volume,
                      avg_sales_price
               FROM price_points
               WHERE market_price IS NOT NULL
               ORDER BY card_id, printing, obs_date ASC"""
        ):
            asp = row["avg_sales_price"]
            out.setdefault((row["card_id"], row["printing"]), []).append(
                (
                    row["obs_date"],
                    float(row["market_price"]),
                    float(row["sales_volume"] or 0),
                    float(asp) if asp else None,
                )
            )
        return out

    def change_over_days(self, days: int) -> dict[tuple[str, str], float]:
        """% change from the close nearest `days` before the latest close, per series.

        Used as the fallback for the API's change_* fields, which are not
        always present. Nearest-earlier close within a 3-day tolerance, same
        rule as invest._change_over.
        """
        latest = self.latest_obs_date()
        if not latest:
            return {}
        target = (date.fromisoformat(latest) - timedelta(days=days)).isoformat()
        floor = (date.fromisoformat(target) - timedelta(days=3)).isoformat()
        out: dict[tuple[str, str], float] = {}
        rows = self.conn.execute(
            """WITH now AS (
                 SELECT card_id, printing, market_price
                 FROM price_points p
                 WHERE obs_date = (SELECT MAX(obs_date) FROM price_points q
                                   WHERE q.card_id=p.card_id AND q.printing=p.printing
                                     AND q.market_price IS NOT NULL)
                   AND market_price IS NOT NULL
               ), then_ AS (
                 SELECT card_id, printing, market_price
                 FROM price_points p
                 WHERE obs_date = (SELECT MAX(obs_date) FROM price_points q
                                   WHERE q.card_id=p.card_id AND q.printing=p.printing
                                     AND q.obs_date <= ? AND q.obs_date >= ?
                                     AND q.market_price IS NOT NULL)
                   AND market_price IS NOT NULL
               )
               SELECT now.card_id, now.printing,
                      (now.market_price / then_.market_price - 1) * 100 AS pct
               FROM now JOIN then_ ON then_.card_id=now.card_id AND then_.printing=now.printing
               WHERE then_.market_price > 0""",
            (target, floor),
        )
        for r in rows:
            out[(r["card_id"], r["printing"])] = r["pct"]
        return out

    def cards_needing_history(self, min_price: float, limit: int) -> list[sqlite3.Row]:
        """Cards above a price floor with the least history -- backfill these first."""
        return self.conn.execute(
            """SELECT c.id AS card_id, c.name,
                      MAX(p.market_price) AS px,
                      SUM(CASE WHEN p.source='history' THEN 1 ELSE 0 END) AS hist_points
               FROM cards c
               JOIN price_points p ON p.card_id = c.id
               GROUP BY c.id
               HAVING px >= ? AND hist_points = 0
               ORDER BY px DESC
               LIMIT ?""",
            (min_price, limit),
        ).fetchall()

    def market_breadth(self, obs_date: str | None = None) -> dict[str, Any]:
        """How much of the whole market is moving, before any filters."""
        obs_date = obs_date or self.latest_obs_date()
        if not obs_date:
            return {}
        # Same latest-per-card rule as latest_prices -- breadth measured on one
        # date would describe whichever half of the market the batch happened to
        # touch that day.
        rows = self.latest_prices(obs_date)
        priced = [r for r in rows if r["market_price"] is not None]
        return {
            "priced": len(priced),
            "up_7d": sum(1 for r in priced if (r["change_7d"] or 0) > 0),
            "down_7d": sum(1 for r in priced if (r["change_7d"] or 0) < 0),
            "up_24h": sum(1 for r in priced if (r["change_24h"] or 0) > 0),
        }

    def flagged_card_ids(self, obs_date: str, limit: int = 500) -> list[str]:
        rows = self.conn.execute(
            "SELECT card_id FROM alerts WHERE obs_date=? ORDER BY score DESC LIMIT ?",
            (obs_date, limit),
        ).fetchall()
        return [r["card_id"] for r in rows]

    def card_by_tcgplayer_id(self, tcgplayer_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM cards WHERE tcgplayer_id=?", (tcgplayer_id,)
        ).fetchone()

    def stats(self) -> dict[str, Any]:
        q = self.conn.execute
        return {
            "sets": q("SELECT COUNT(*) n FROM sets").fetchone()["n"],
            "cards": q("SELECT COUNT(*) n FROM cards").fetchone()["n"],
            "price_points": q("SELECT COUNT(*) n FROM price_points").fetchone()["n"],
            "snapshot_dates": q(
                "SELECT COUNT(DISTINCT obs_date) n FROM price_points WHERE source='snapshot'"
            ).fetchone()["n"],
            "latest": self.latest_obs_date(),
            "runs": q("SELECT COUNT(*) n FROM runs").fetchone()["n"],
        }


def _float_or_none(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # drop NaN


def _int_or_none(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
