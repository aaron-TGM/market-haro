"""Card art, embedded.

WHY THE PAGE CARRIES ITS OWN IMAGES

TCGplayer's image CDN serves card art to any origin -- no hotlink check, no
referrer rule; that was tested from a foreign origin in a real browser. The
images still "break" in one place that matters: any sandboxed preview (the
in-app file viewer, a mail client, a screenshot renderer) that refuses to
load third-party hosts. A subscriber who opens the report from an email
attachment or a preview pane sees grey boxes and concludes the product is
broken.

So the row thumbnails are embedded as data URIs. 240px-wide WebP at quality
70 is about 15 KB a card, ~2 MB for a full issue -- the same order as the
price series already on the page, and it makes the file work with the network
unplugged. The detail panel asks the CDN for a 1000px copy and falls back to
the embedded thumbnail if that fails, so a real browser gets the sharp image
and a sandbox still gets a picture.

Fetched art is cached under data/images/ (gitignored). Rendering never
requires the network: with fetch=False, cards without a cached image simply
keep their remote URL.
"""

from __future__ import annotations

import base64
import io
import re
from pathlib import Path
from typing import Iterable

CDN = "https://product-images.tcgplayer.com/fit-in/{size}x{size}/{id}.jpg"
FETCH_SIZE = 400        # what we ask the CDN for
THUMB_WIDTH = 240       # 2x the 120px row art
THUMB_QUALITY = 70
_ID = re.compile(r"/(\d+)\.jpg")


def product_id(row: dict) -> int | None:
    """tcgplayer product id from the row, or from its image URL."""
    pid = row.get("tcgplayer_id")
    if isinstance(pid, int) and pid > 0:
        return pid
    m = _ID.search(row.get("image_url") or "")
    return int(m.group(1)) if m else None


def large_url(pid: int) -> str:
    return CDN.format(size=1000, id=pid)


def _fetch(pid: int, timeout: float = 15.0) -> bytes | None:
    try:
        import requests

        r = requests.get(CDN.format(size=FETCH_SIZE, id=pid), timeout=timeout,
                         headers={"User-Agent": "market-haro/1.0"})
        if r.ok and r.content[:2] == b"\xff\xd8":
            return r.content
    except Exception:  # network is optional; the page renders without it
        return None
    return None


def _to_webp(jpeg: bytes) -> tuple[bytes, str]:
    """Resize + recompress. Without Pillow, ship the JPEG as fetched."""
    try:
        from PIL import Image
    except ImportError:
        return jpeg, "image/jpeg"
    im = Image.open(io.BytesIO(jpeg)).convert("RGB")
    if im.width > THUMB_WIDTH:
        im = im.resize((THUMB_WIDTH, round(im.height * THUMB_WIDTH / im.width)), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "WEBP", quality=THUMB_QUALITY, method=6)
    return out.getvalue(), "image/webp"


def thumb(pid: int, cache: Path, *, fetch: bool = True) -> tuple[bytes, str] | None:
    cache.mkdir(parents=True, exist_ok=True)
    webp = cache / f"{pid}.webp"
    if webp.exists():
        return webp.read_bytes(), "image/webp"
    jpg = cache / f"{pid}.jpg"
    raw = jpg.read_bytes() if jpg.exists() else (_fetch(pid) if fetch else None)
    if not raw:
        return None
    if not jpg.exists():
        jpg.write_bytes(raw)
    data, mime = _to_webp(raw)
    if mime == "image/webp":
        webp.write_bytes(data)
    return data, mime


def embed(rows: Iterable[dict], cache: Path, *, fetch: bool = True) -> int:
    """Attach `thumb` (data URI) and `image_large` (CDN URL) to each row in place.

    Returns how many rows got an embedded thumbnail.
    """
    n = 0
    for r in rows:
        pid = product_id(r)
        if pid is None:
            continue
        r["image_large"] = large_url(pid)
        got = thumb(pid, cache, fetch=fetch)
        if got:
            data, mime = got
            r["thumb"] = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
            n += 1
    return n
