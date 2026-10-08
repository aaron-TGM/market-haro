"""TCGplayer's affiliate program, through Impact: the tag, and what the page must say about it.

WHAT THE TAG DOES

Impact gives each partner account one script (its "Universal Tracking Tag").
Loaded in the <head>, it records the page view (`trackImpression`) and
rewrites every link to a brand the account is approved for -- here, links to
tcgplayer.com -- into an Impact tracking link that lands on the same page
(`transformLinks`). A subscriber who clicks through and buys within TCGplayer's
window earns Market Haro a commission; the price they pay is the same.

The report draws its rows with JavaScript and adds the "Open on TCGplayer"
button only when a row opens, so the page asks the tag to look again after
every redraw (haro.JS `retrack`). Links it has already rewritten are left
alone, so asking twice is harmless.

The snippet below is Impact's, unchanged; only the script URL comes from
config (`affiliate.impact_utt`). The URL is public -- every visitor's browser
loads it -- and is checked against Impact's own pattern so a typo in config
cannot put anything else on the page. Empty means no tag, plain links, and no
disclosure.

WHAT THE PAGE MUST SAY

TCGplayer's Partner Guidelines (April 2025) ask for a disclosure that is
"clear, conspicuous, prominent and unambiguous", and the FTC's Endorsement
Guides put it before the first link, not only in a footer. So the report says
it above the list and beside the button, and both pages say in the footer
that the tag is there and what it records.
"""

from __future__ import annotations

import re

_UTT = re.compile(r"^https://utt\.impactcdn\.com/[A-Za-z0-9-]+\.js$")

DISCLOSURE = ("Links to TCGplayer on this page are affiliate links: Market Haro earns a commission "
              "on what you buy through them, at no cost to you. It never affects the ranking.")
BUTTON_NOTE = "affiliate link"
FOOTER = ("Market Haro takes part in TCGplayer’s affiliate program through Impact; Impact’s tag on "
          "this page records visits and rewrites links to TCGplayer into tracked links.")


def utt_url(cfg: dict | None) -> str:
    """The configured tag URL, or "" when it is missing or not Impact's."""
    url = str((cfg or {}).get("impact_utt") or "").strip()
    return url if _UTT.match(url) else ""


def head_tag(cfg: dict | None) -> str:
    """Impact's snippet for the <head>, verbatim, or "" when no tag is configured."""
    url = utt_url(cfg)
    if not url:
        return ""
    return ("<script type=\"text/javascript\">(function(i,m,p,a,c,t){c.ire_o=p;c[p]=c[p]||function(){"
            "(c[p].a=c[p].a||[]).push(arguments)};t=a.createElement(m);var z=a.getElementsByTagName(m)[0];"
            "t.async=1;t.src=i;z.parentNode.insertBefore(t,z)})('" + url + "','script','impactStat',"
            "document,window);impactStat('transformLinks');impactStat('trackImpression');</script>")
