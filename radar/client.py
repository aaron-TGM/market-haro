"""Thin, defensive client for the tcgapi.dev v1 REST API.

Design notes:
  * The API returns its payload under varying keys depending on endpoint
    (`data`, `cards`, `sets`, `prices`, ...). `_unwrap` normalises that so the
    rest of the codebase only ever sees plain lists/dicts.
  * Every response carries a `rate_limit` block; we track it and stop the run
    before blowing the daily quota rather than after.
  * 429 and 5xx get exponential backoff with jitter. 404 returns None instead of
    raising, because "this card has no history yet" is a normal outcome.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Iterator

import requests

log = logging.getLogger("radar.client")


class RateLimitExhausted(RuntimeError):
    """Raised when the daily quota is spent (or reserved headroom is reached)."""


class APIError(RuntimeError):
    pass


LIST_KEYS = ("data", "results", "items", "cards", "sets", "games", "prices", "movers")


def _unwrap(payload: Any) -> Any:
    """Return the meaningful body of a response, whatever key it hides under."""
    if not isinstance(payload, dict):
        return payload
    for key in LIST_KEYS:
        if key in payload and isinstance(payload[key], (list, dict)):
            return payload[key]
    # Some single-object endpoints return the object at the top level.
    return payload


class TCGClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.tcgapi.dev/v1",
        *,
        timeout: int = 30,
        max_retries: int = 4,
        daily_budget: int = 10_000,
        reserve: int = 500,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.daily_budget = daily_budget
        self.reserve = reserve

        self.requests_made = 0
        self.daily_remaining: int | None = None

        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-API-Key": api_key,
                "Accept": "application/json",
                "User-Agent": "gundam-price-radar/1.0",
            }
        )

    # -- budget -----------------------------------------------------------------
    @property
    def budget_left(self) -> int:
        """Best available estimate of usable requests remaining."""
        if self.daily_remaining is not None:
            return max(0, self.daily_remaining - self.reserve)
        return max(0, self.daily_budget - self.reserve - self.requests_made)

    def _check_budget(self) -> None:
        if self.budget_left <= 0:
            raise RateLimitExhausted(
                f"Daily request budget reached (made {self.requests_made} this run, "
                f"api reports {self.daily_remaining} remaining, "
                f"reserving {self.reserve}). Try again after the quota resets."
            )

    # -- core -------------------------------------------------------------------
    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        allow_404: bool = True,
    ) -> Any:
        self._check_budget()
        url = f"{self.base_url}/{path.lstrip('/')}"
        delay = 1.0
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = self.session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:  # network hiccup
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(delay + random.uniform(0, 0.4))
                delay *= 2
                continue

            self.requests_made += 1

            if resp.status_code == 404 and allow_404:
                return None

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", delay))
                if attempt >= self.max_retries:
                    raise RateLimitExhausted(
                        f"429 from {url} after {attempt + 1} attempts."
                    )
                log.warning("429 on %s -- sleeping %.1fs", path, retry_after)
                time.sleep(min(retry_after, 60) + random.uniform(0, 0.4))
                delay *= 2
                continue

            if 500 <= resp.status_code < 600:
                last_error = APIError(f"{resp.status_code} from {url}: {resp.text[:200]}")
                if attempt >= self.max_retries:
                    break
                time.sleep(delay + random.uniform(0, 0.4))
                delay *= 2
                continue

            if resp.status_code == 401 or resp.status_code == 403:
                raise APIError(
                    f"{resp.status_code} from {url} -- check TCGAPI_KEY and that your "
                    f"plan covers this endpoint. Body: {resp.text[:300]}"
                )

            if not resp.ok:
                raise APIError(f"{resp.status_code} from {url}: {resp.text[:300]}")

            try:
                payload = resp.json()
            except ValueError as exc:
                raise APIError(f"Non-JSON response from {url}: {resp.text[:200]}") from exc

            self._track_rate_limit(payload, resp)
            return payload

        raise APIError(f"Request to {url} failed after retries: {last_error}")

    def _track_rate_limit(self, payload: Any, resp: requests.Response) -> None:
        if isinstance(payload, dict):
            rl = payload.get("rate_limit")
            if isinstance(rl, dict) and rl.get("daily_remaining") is not None:
                try:
                    self.daily_remaining = int(rl["daily_remaining"])
                    return
                except (TypeError, ValueError):
                    pass
        header = resp.headers.get("X-RateLimit-Remaining")
        if header is not None:
            try:
                self.daily_remaining = int(header)
            except ValueError:
                pass

    def get(self, path: str, **params: Any) -> Any:
        params = {k: v for k, v in params.items() if v is not None}
        return _unwrap(self.request("GET", path, params=params))

    def get_raw(self, path: str, **params: Any) -> Any:
        params = {k: v for k, v in params.items() if v is not None}
        return self.request("GET", path, params=params)

    def post(self, path: str, body: Any) -> Any:
        return _unwrap(self.request("POST", path, json_body=body))

    # -- pagination -------------------------------------------------------------
    def paginate(
        self, path: str, *, per_page: int = 100, max_pages: int = 200, **params: Any
    ) -> Iterator[dict]:
        """Yield every item across pages of a paginated list endpoint."""
        page = 1
        while page <= max_pages:
            payload = self.get_raw(path, page=page, per_page=per_page, **params)
            if payload is None:
                return
            items = _unwrap(payload)
            if isinstance(items, dict):
                items = [items]
            if not items:
                return
            for item in items:
                yield item
            # tcgapi.dev returns meta: {total, page, per_page, has_more}
            meta = payload.get("meta") or payload.get("pagination") or {}
            if isinstance(meta, dict) and "has_more" in meta:
                if not meta["has_more"]:
                    return
            elif len(items) < per_page:
                return
            page += 1

    # -- typed helpers ----------------------------------------------------------
    def games(self) -> list[dict]:
        out = self.get("/games")
        return out if isinstance(out, list) else [out] if out else []

    def sets(self, game_slug: str) -> list[dict]:
        return list(self.paginate("/sets", game=game_slug))

    def set_cards(self, set_id: Any) -> list[dict]:
        return list(self.paginate(f"/sets/{set_id}/cards"))

    def set_prices(self, set_id: Any) -> list[dict]:
        """Pro tier: every price row for a set in one request."""
        out = self.get(f"/sets/{set_id}/prices")
        if out is None:
            return []
        return out if isinstance(out, list) else [out]

    def card_history(self, card_id: Any, range_: str = "year") -> list[dict]:
        out = self.get(f"/cards/{card_id}/history", range=range_)
        if out is None:
            return []
        if isinstance(out, dict):
            # e.g. {"history": [...]} already unwrapped, or {"Normal": [...]}
            flattened: list[dict] = []
            for key, value in out.items():
                if isinstance(value, list):
                    for row in value:
                        if isinstance(row, dict):
                            row.setdefault("printing", key)
                            flattened.append(row)
            return flattened
        return out

    def card_by_tcgplayer_id(self, tcgplayer_id: int) -> dict | None:
        out = self.get(f"/cards/tcgplayer/{tcgplayer_id}")
        if isinstance(out, list):
            return out[0] if out else None
        return out

    def top_movers(
        self,
        game_slug: str,
        *,
        direction: str = "up",
        period: str = "24h",
        limit: int = 50,
        type_: str | None = None,
    ) -> list[dict]:
        out = self.get(
            "/prices/top-movers",
            game=game_slug,
            direction=direction,
            period=period,
            limit=limit,
            type=type_,
        )
        return out if isinstance(out, list) else []

    def bulk_prices(self, card_ids: list[Any]) -> list[dict]:
        """Pro tier: up to 500 card ids per call."""
        out: list[dict] = []
        for i in range(0, len(card_ids), 500):
            chunk = card_ids[i : i + 500]
            res = self.get("/bulk/prices", ids=",".join(str(c) for c in chunk))
            if isinstance(res, list):
                out.extend(res)
            elif isinstance(res, dict):
                for key, value in res.items():
                    if isinstance(value, list):
                        for row in value:
                            if isinstance(row, dict):
                                row.setdefault("card_id", key)
                                out.append(row)
        return out
