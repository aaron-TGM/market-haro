"""Publish to Ghost: the digest as a paid-members email, the report as a page.

WHY GHOST

It does the four things a paid daily needs -- Stripe memberships, member-only
content, the email send, and magic-link sign-in -- in one place with one API.
Building those on top of a static host means reimplementing them, and the
version you build in a week is worse than the one Ghost has been shipping for
years. This module is ~150 lines because Ghost is doing the work.

WHAT IT PUBLISHES, EACH DAY

  1. A POST, visibility `paid`, sent as email to the paid-members segment.
     Body is the digest HTML from `digest.to_html` with a button to the report.
  2. A PAGE, visibility `paid`, holding the full dashboard HTML in a single
     HTML card. Pages are not emailed and do not appear in the post feed; they
     are the thing the button links to. Same slug every day (`market-haro`), so
     the link in yesterday's email opens today's report -- that is what a
     subscriber wants from a "latest report" link.

Ghost's Admin API wants a short-lived JWT signed with the admin key. The key is
`<id>:<hex secret>`; the token is HS256 with the id as `kid`, a five-minute
expiry, and audience `/admin/`. No third-party JWT library -- it is forty lines
of stdlib, and one fewer dependency to keep patched.

WHAT IT DOES NOT DO

It does not create members, take payments, or send anything to free members.
Those are Ghost settings, deliberately outside this code. If the newsletter
segment or visibility ever needs to change it is one setting in the Ghost
admin, not a redeploy.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from urllib import request as _rq
from urllib.error import HTTPError

API_VERSION = "v5.0"
REPORT_SLUG = "market-haro"


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def token(admin_key: str, *, now: float | None = None) -> str:
    """HS256 JWT for the Admin API. Valid five minutes; Ghost rejects longer."""
    try:
        kid, secret_hex = admin_key.split(":", 1)
        secret = bytes.fromhex(secret_hex)
    except ValueError as exc:
        raise ValueError("GHOST_ADMIN_KEY must look like '<id>:<hex secret>'") from exc
    iat = int(now if now is not None else time.time())
    header = {"alg": "HS256", "typ": "JWT", "kid": kid}
    payload = {"iat": iat, "exp": iat + 5 * 60, "aud": "/admin/"}
    signing = ".".join(
        _b64url(json.dumps(x, separators=(",", ":")).encode()) for x in (header, payload)
    )
    sig = hmac.new(secret, signing.encode(), hashlib.sha256).digest()
    return f"{signing}.{_b64url(sig)}"


class Ghost:
    def __init__(self, url: str, admin_key: str, *, timeout: int = 30) -> None:
        self.base = url.rstrip("/") + "/ghost/api/admin"
        self.admin_key = admin_key
        self.timeout = timeout
        self.requests_made = 0

    def _call(self, method: str, path: str, body: dict | None = None, **query) -> dict:
        url = self.base + path
        if query:
            from urllib.parse import urlencode

            url += "?" + urlencode(query)
        data = json.dumps(body).encode() if body is not None else None
        req = _rq.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Ghost {token(self.admin_key)}")
        req.add_header("Accept-Version", API_VERSION)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        self.requests_made += 1
        try:
            with _rq.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"Ghost {method} {path} -> {exc.code}: {detail}") from exc

    # -- pages: the report ----------------------------------------------------
    def find_page(self, slug: str) -> dict | None:
        out = self._call("GET", f"/pages/slug/{slug}/")
        pages = out.get("pages") or []
        return pages[0] if pages else None

    def upsert_report_page(self, html: str, *, title: str, slug: str = REPORT_SLUG,
                           visibility: str = "paid") -> dict:
        """Create or update a page from raw HTML: the members-only report, or
        the public track record (`visibility="public"`).

        Ghost stores content as Lexical; an HTML card keeps the dashboard's
        markup, styles and script intact instead of having them 'cleaned'.
        """
        lexical = json.dumps({
            "root": {
                "children": [{"type": "html", "version": 1, "html": html}],
                "direction": None, "format": "", "indent": 0, "type": "root", "version": 1,
            }
        })
        existing = self.find_page(slug)
        body = {"title": title, "slug": slug, "lexical": lexical,
                "status": "published", "visibility": visibility}
        if existing:
            body["updated_at"] = existing["updated_at"]
            out = self._call("PUT", f"/pages/{existing['id']}/", {"pages": [body]})
        else:
            out = self._call("POST", "/pages/", {"pages": [body]})
        return (out.get("pages") or [{}])[0]

    # -- posts: the digest, emailed --------------------------------------------
    def publish_digest(
        self,
        html: str,
        *,
        title: str,
        slug: str,
        segment: str = "status:-free",
        email: bool = True,
    ) -> dict:
        """Publish the day's digest as a paid post and email it.

        `segment` is Ghost's filter syntax; `status:-free` is every paying
        member. `email=False` publishes to the site without sending -- useful
        for a dry run or a re-issue.
        """
        lexical = json.dumps({
            "root": {
                "children": [{"type": "html", "version": 1, "html": html}],
                "direction": None, "format": "", "indent": 0, "type": "root", "version": 1,
            }
        })
        body = {"title": title, "slug": slug, "lexical": lexical,
                "status": "published", "visibility": visibility}
        query: dict[str, Any] = {}
        if email:
            body["email_segment"] = segment
            query["newsletter"] = self._default_newsletter_slug()
            query["email_segment"] = segment
        out = self._call("POST", "/posts/", {"posts": [body]}, **query)
        return (out.get("posts") or [{}])[0]

    def _default_newsletter_slug(self) -> str:
        out = self._call("GET", "/newsletters/", limit=50)
        active = [n for n in (out.get("newsletters") or []) if n.get("status") == "active"]
        if not active:
            raise RuntimeError("Ghost has no active newsletter to send through")
        return active[0]["slug"]

    def site(self) -> dict:
        return self._call("GET", "/site/").get("site") or {}
