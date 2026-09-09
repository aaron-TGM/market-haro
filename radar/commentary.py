"""The words on the page, written by a model that is only allowed the facts.

WHY

The first version of every card's case was a template: one sentence with the
numbers dropped into slots. Every card sounded the same and none of them said
the thing a person would say. So the prose is now written by a language model
-- but a model that is handed nothing except the card's measured facts and the
house voice (docs/VOICE.md), and whose output is checked, number by number,
against those facts before it is allowed on the page.

THE GUARD

Every number in the output must appear in the input, allowing the usual
roundings (69.22 -> 69, 86.0 -> 86, -12.4 -> 12). A sentence with a number the
facts do not contain is rejected and the template takes its place. This is
what makes it safe to publish 130 of these a day without a person reading
each one: the model can be wrong about emphasis, never about a figure.

WHAT IT WRITES

  card     the case (2-3 sentences) and the watch (1-2), per ranked card
  lead     the email's opening paragraph, from the day's diff
  note     a draft of the weekly note, for a person to edit, never published
           on its own

CACHE, COST, FAILURE

Results are cached per issue date in data/commentary/<date>.json, keyed by a
hash of the facts, so re-rendering an issue costs nothing and an unchanged
card is never rewritten. Roughly a dollar a day on the small model. No API
key, no network, a refused sentence: the template. The issue always goes out.

PROVIDERS

OpenAI is the default (`commentary.provider: openai`, model gpt-5.6-sol --
the one that writes best, and the reason this exists); Anthropic is the
alternative. Both are called with `requests`, no SDK. Keys come from the
environment only -- OPENAI_API_KEY or ANTHROPIC_API_KEY -- never from config.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Sequence

PROVIDERS = {
    "openai": {"url": "https://api.openai.com/v1/chat/completions", "env": "OPENAI_API_KEY", "model": "gpt-5.6-sol"},
    "anthropic": {"url": "https://api.anthropic.com/v1/messages", "env": "ANTHROPIC_API_KEY", "model": "claude-haiku-4-5"},
}
DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = PROVIDERS[DEFAULT_PROVIDER]["model"]
ANTHROPIC_VERSION = "2023-06-01"
MAX_WORKERS = 6

_VOICE_PATH = Path(__file__).resolve().parent.parent / "docs" / "VOICE.md"


def voice() -> str:
    try:
        return _VOICE_PATH.read_text(encoding="utf-8")
    except OSError:
        return "Write plainly, lead with the point, use only the numbers you are given, no advice, no forecasts."


# ---------------------------------------------------------------- the guard
_NUM = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?%?")


def _numbers_in(obj: Any, out: set[float]) -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        v = abs(float(obj))
        out.update({v, round(v), round(v, 1), round(v, 2)})
        if v >= 1000:
            out.add(round(v / 1000, 1))  # "$1.6k"
        return
    if isinstance(obj, str):
        for m in _NUM.findall(obj):
            try:
                v = abs(float(m.rstrip("%").replace(",", "")))
            except ValueError:
                continue
            out.update({v, round(v), round(v, 1)})
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _numbers_in(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numbers_in(v, out)


ALWAYS_OK = {float(i) for i in range(0, 32)} | {2025.0, 2026.0, 2027.0, 50.0, 100.0}


def guard(text: str, facts: Any) -> tuple[bool, list[str]]:
    """Every number in `text` must be in `facts` (with rounding). Returns (ok, offenders)."""
    allowed: set[float] = set()
    _numbers_in(facts, allowed)
    bad = []
    for m in _NUM.findall(text or ""):
        raw = m.rstrip("%").replace(",", "")
        try:
            v = abs(float(raw))
        except ValueError:
            continue
        if v in ALWAYS_OK or v in allowed or round(v) in allowed or round(v, 1) in allowed:
            continue
        bad.append(m)
    return (not bad), bad


BANNED = re.compile(r"\b(should|will|likely|expect(?:ed|s)?|buy now|guaranteed|investors)\b", re.I)


def tone_ok(text: str) -> bool:
    return not BANNED.search(text or "") and "!" not in (text or "")


# ---------------------------------------------------------------- facts
def card_facts(r: dict, *, releases: Sequence[dict] = (), playbook: dict | None = None) -> dict:
    """The only thing the model sees for a card. Every number here is measured."""
    def f(k):
        v = r.get(k)
        return round(v, 1) if isinstance(v, float) else v

    keys = ("name", "set_name", "number", "rarity", "printing", "rank", "invest_score",
            "market_price", "floor_low", "shelf_med", "copies", "settled_price", "ask_premium_pct",
            "settled_days", "settled_volume", "change_3d", "change_7d", "change_30d", "change_90d",
            "change_180d", "change_1y", "consistency_pct", "volatility_pct", "drawdown_pct",
            "avg_daily_sales", "days_traded_pct", "entry_vs_shelf_pct", "listings_change_7d", "listings_change_30d",
            "days_of_shelf", "dollars_to_clear", "dollars_30d", "tracked_high", "tracked_high_date", "tracked_since",
            "off_tracked_high_pct", "kind", "release_date",
            "days_since_release", "first_price", "first_date", "change_since_first", "total_listings")
    facts = {k: f(k) for k in keys if r.get(k) is not None}
    if r.get("kind") == "sealed":            # sealed is not scored and has no rarity
        facts.pop("invest_score", None); facts.pop("rarity", None)
    elif facts.get("rarity") in ("—", "None"):
        facts.pop("rarity", None)
    if r.get("components"):
        facts["score_components"] = {k: round(v) for k, v in r["components"].items()}
    if r.get("set_depth"):
        facts["set_beneath_it"] = r["set_depth"]
    ser = r.get("series") or []
    if ser:
        facts["window"] = {"from": ser[0][0], "to": ser[-1][0], "first_price": round(ser[0][1], 2),
                           "last_price": round(ser[-1][1], 2), "high": round(max(p[1] for p in ser), 2)}
        lo, hi = ser[0][0], ser[-1][0]
        facts["releases_in_window"] = [{"date": m["date"], "label": m["label"]} for m in releases if lo <= m["date"] <= hi]
    nxt = next((m for m in releases if ser and m["date"] > ser[-1][0]), None)
    if nxt:
        facts["next_release"] = {"date": nxt["date"], "label": nxt["label"]}
    if playbook and playbook.get("summary"):
        s = playbook["summary"]
        facts["playbook_medians"] = {
            "prior_set_top20_30d": s["prior"]["d30"][0], "new_set_top20_30d": s["new"]["d30"][0],
            "new_set_top20_60d": s["new"]["d60"][0], "market_30d": s["market"]["d30"][0],
            "releases_measured": s["prior"]["d30"][1]}
    return facts


def lead_facts(diff: dict, *, index: dict | None, releases: Sequence[dict], obs_date: str, today: str,
               depth: Sequence[dict] = ()) -> dict:
    top = lambda rows, n=5: [{k: r.get(k) for k in ("name", "set_name", "rank", "prev_rank", "invest_score",  # noqa: E731
                                                     "ask_premium_pct", "prev_premium", "floor_low", "disqualified")
                              if r.get(k) is not None} for r in (rows or [])[:n]]
    ix = index or {}
    nxt = next((m for m in releases if m["date"] > obs_date), None)
    return {
        "issue_date": obs_date, "run_date": today, "feed_late": diff.get("feed_late"),
        "candidates": diff.get("candidates"), "screened_out": diff.get("screened"),
        "breadth_now_pct": (diff.get("breadth") or {}).get("now_pct"),
        "breadth_prev_pct": (diff.get("breadth") or {}).get("prev_pct"),
        "index": {k: ix.get(k) for k in ("name", "value", "change_1d", "change_7d", "change_30d", "change_90d",
                                         "high", "high_date", "up_7d", "measured_7d") if ix.get(k) is not None},
        "entered_top_20": top(diff.get("entered")), "left_top_20": top(diff.get("exited")),
        "climbers": top(diff.get("climbers")), "fallers": top(diff.get("fallers")),
        "asks_ran_ahead": top(diff.get("stretched")), "asks_fell_below": top(diff.get("cheapened")),
        "next_release": ({"date": nxt["date"], "label": nxt["label"], "names": nxt.get("names")} if nxt else None),
        "money_by_set_30d": list(depth) or None,
    }


# ---------------------------------------------------------------- the model
class Client:
    """One thin call per provider. `complete(system, user)` -> text."""

    def __init__(self, api_key: str | None = None, *, provider: str = DEFAULT_PROVIDER,
                 model: str | None = None, timeout: float = 90.0):
        if provider not in PROVIDERS:
            raise ValueError(f"unknown commentary provider {provider!r}; one of {sorted(PROVIDERS)}")
        self.provider = provider
        self.api_key = api_key or os.getenv(PROVIDERS[provider]["env"])
        self.model = model or PROVIDERS[provider]["model"]
        self.timeout = timeout
        self.calls = 0
        self.tokens_in = 0
        self.tokens_out = 0

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def complete(self, system: str, user: str, *, max_tokens: int = 400) -> str:
        import requests

        url = PROVIDERS[self.provider]["url"]
        if self.provider == "openai":
            r = requests.post(url, timeout=self.timeout,
                              headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                              json={"model": self.model, "max_completion_tokens": max_tokens,
                                    "messages": [{"role": "system", "content": system},
                                                 {"role": "user", "content": user}]})
            r.raise_for_status()
            out = r.json()
            self.calls += 1
            u = out.get("usage") or {}
            self.tokens_in += int(u.get("prompt_tokens") or 0)
            self.tokens_out += int(u.get("completion_tokens") or 0)
            choice = (out.get("choices") or [{}])[0]
            return str(((choice.get("message") or {}).get("content")) or "").strip()

        r = requests.post(url, timeout=self.timeout, headers={
            "x-api-key": self.api_key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"},
            json={"model": self.model, "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": user}]})
        r.raise_for_status()
        out = r.json()
        self.calls += 1
        u = out.get("usage") or {}
        self.tokens_in += int(u.get("input_tokens") or 0)
        self.tokens_out += int(u.get("output_tokens") or 0)
        return "".join(b.get("text", "") for b in out.get("content") or [] if b.get("type") == "text").strip()


class RelayPending(Exception):
    """The relay has no answer for this request yet; it has been queued."""


class RelayClient(Client):
    """A client for machines that cannot reach the API.

    `complete()` answers from `<dir>/responses.json` ({request id: text}) when the
    answer is there, and otherwise appends the request to `<dir>/requests.json`
    and raises RelayPending, so the template stands for that row. Something
    with network -- a browser page, another machine -- turns requests into
    responses (scripts/relay.html does it from a browser tab), and the next run
    finds them. Request ids are the hash of (model, system, user), so the same
    facts always map to the same answer.
    """

    def __init__(self, directory: Path | str, *, model: str | None = None, provider: str = DEFAULT_PROVIDER,
                 replace: bool = False):
        """replace=True: the queue is rebuilt from this run alone (an issue asks for
        every card, so yesterday's requests are stale); False appends (a note draft
        adds one request to whatever the issue queued)."""
        super().__init__("relay", provider=provider, model=model)
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.responses = self._read("responses.json")
        self.queued: dict[str, dict] = ({} if replace else
                                        {r["id"]: r for r in self._read("requests.json").get("requests", [])})
        self.answered = 0

    def _read(self, name: str) -> dict:
        p = self.dir / name
        try:
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except (ValueError, OSError):
            return {}

    @staticmethod
    def request_id(model: str, system: str, user: str) -> str:
        return hashlib.sha256("\x00".join((model, system, user)).encode()).hexdigest()[:16]

    def complete(self, system: str, user: str, *, max_tokens: int = 400) -> str:
        rid = self.request_id(self.model, system, user)
        hit = self.responses.get(rid)
        if isinstance(hit, str) and hit.strip():
            self.calls += 1
            self.answered += 1
            return hit.strip()
        self.queued[rid] = {"id": rid, "model": self.model, "system": system, "user": user, "max_tokens": max_tokens}
        raise RelayPending(rid)

    def flush(self) -> int:
        """Write the queue (deduplicated, system prompts shared) and return its size."""
        reqs = sorted(self.queued.values(), key=lambda r: r["id"])
        (self.dir / "requests.json").write_text(
            json.dumps({"provider": self.provider, "model": self.model, "requests": reqs},
                       ensure_ascii=False) + "\n", encoding="utf-8")
        return len(reqs)


def from_config(cfg_block: dict | None, *, relay: str | None = None, relay_replace: bool = False) -> Client:
    """The client the pipeline uses, from the `commentary:` block of config.yaml."""
    c = cfg_block or {}
    provider = c.get("provider") or DEFAULT_PROVIDER
    model = c.get("model") or PROVIDERS.get(provider, {}).get("model")
    if relay:
        return RelayClient(relay, provider=provider, model=model, replace=relay_replace)
    return Client(provider=provider, model=model)


def _system(task: str) -> str:
    return (voice() + "\n\n---\n\nTASK\n" + task +
            "\n\nHARD RULES\n- Use only the numbers in the facts. Do not compute new ones. Do not round a fact into a different fact."
            "\n- No advice, no forecasts, no 'should', 'will', 'expect', 'likely'. The reader is 'you', never 'investors'."
            "\n- No exclamation marks, no emoji, no headings, no bullet points unless the task says so."
            "\n- If the facts are unremarkable, say so in one sentence rather than inventing drama.")


CARD_TASK = ("Write the case for this one card, then the watch. Return JSON only: "
             '{"case": "<2-3 sentences>", "watch": "<1-2 sentences: the concrete condition that would change the case>"}. '
             "The case leads with the situation, then two or three numbers as evidence. "
             "Mention a release mark or the playbook medians only when they bear on this card.")

LEAD_TASK = ("Write the opening paragraph of today's issue email: 80-120 words, one paragraph, plain text. "
             "Lead with what the market did, then the two or three moves that matter, then the next release if it is within 21 days. "
             "Name cards the way players do.")

NOTE_TASK = ("Draft this week's note for a person to edit: 250-400 words in Markdown, two or three short paragraphs and, "
             "if useful, a list of two or three things to watch. A point of view, not a recap. "
             "Say plainly that price data cannot see reprints, bans or tournament results. Never mention that this is a draft.")


# ---------------------------------------------------------------- cache
def _cache_path(root: Path, date: str) -> Path:
    return Path(root) / "commentary" / f"{date}.json"


def _load(root: Path, date: str) -> dict:
    p = _cache_path(root, date)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (ValueError, OSError):
        return {}


def _save(root: Path, date: str, cache: dict) -> None:
    p = _cache_path(root, date)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cache, indent=0, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _fingerprint(facts: Any) -> str:
    return hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _parse_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


# ---------------------------------------------------------------- public
def write_cards(rows: Sequence[dict], *, root: Path, date: str, client: Client | None = None,
                releases: Sequence[dict] = (), playbook: dict | None = None,
                key: Callable[[dict], str] = lambda r: f"{r['card_id']}|{r.get('printing') or 'Normal'}") -> dict[str, dict]:
    """key -> {"case", "watch"} for every row the model wrote acceptably. Rows it did not
    (no key, an API error, a number the facts don't contain) are simply absent, and the
    caller keeps the template for them."""
    client = client or Client()
    cache = _load(root, date)
    out: dict[str, dict] = {}
    todo = []
    for r in rows:
        k = key(r)
        facts = card_facts(r, releases=releases, playbook=playbook)
        fp = _fingerprint(facts)
        hit = cache.get(k)
        if hit and hit.get("fp") == fp and hit.get("case"):
            out[k] = {"case": hit["case"], "watch": hit["watch"]}
        else:
            todo.append((k, facts, fp))
    if not client.available or not todo:
        return out

    def one(item):
        k, facts, fp = item
        try:
            text = client.complete(_system(CARD_TASK), "FACTS\n" + json.dumps(facts, ensure_ascii=False), max_tokens=350)
            obj = _parse_json(text)
            if not obj or not obj.get("case"):
                return k, None, "no json"
            case, watch = str(obj.get("case", "")).strip(), str(obj.get("watch", "")).strip()
            ok1, bad1 = guard(case, facts)
            ok2, bad2 = guard(watch, facts)
            if not (ok1 and ok2):
                return k, None, f"numbers not in facts: {bad1 + bad2}"
            if not (tone_ok(case) and tone_ok(watch)):
                return k, None, "tone"
            return k, {"case": case, "watch": watch, "fp": fp}, None
        except Exception as e:  # network, 4xx, timeout: the template stands
            return k, None, str(e)[:120]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for k, rec, why in ex.map(one, todo):
            if rec:
                cache[k] = rec
                out[k] = {"case": rec["case"], "watch": rec["watch"]}
            else:
                cache.setdefault("_rejected", {})[k] = why
    _save(root, date, cache)
    return out


def write_lead(facts: dict, *, root: Path, date: str, client: Client | None = None) -> str | None:
    client = client or Client()
    cache = _load(root, date)
    fp = _fingerprint(facts)
    hit = cache.get("_lead")
    if hit and hit.get("fp") == fp:
        return hit["text"]
    if not client.available:
        return None
    try:
        text = client.complete(_system(LEAD_TASK), "FACTS\n" + json.dumps(facts, ensure_ascii=False), max_tokens=300)
    except Exception:
        return None
    ok, bad = guard(text, facts)
    if not ok or not tone_ok(text) or len(text.split()) < 40:
        cache.setdefault("_rejected", {})["_lead"] = f"numbers not in facts: {bad}" if not ok else "tone/length"
        _save(root, date, cache)
        return None
    cache["_lead"] = {"fp": fp, "text": text}
    _save(root, date, cache)
    return text


def write_note_draft(facts: dict, *, client: Client | None = None) -> str | None:
    """Never cached, never published by the pipeline: written to out/ for a person."""
    client = client or Client()
    if not client.available:
        return None
    try:
        text = client.complete(_system(NOTE_TASK), "FACTS\n" + json.dumps(facts, ensure_ascii=False), max_tokens=900)
    except Exception:
        return None
    ok, bad = guard(text, facts)
    if not ok:
        text = ("<!-- the draft used numbers not in the facts: " + ", ".join(bad) + " — check them before publishing -->\n\n" + text)
    return text
