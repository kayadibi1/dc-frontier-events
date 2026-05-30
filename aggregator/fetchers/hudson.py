"""Layer-2 adapter: Hudson Institute events.

Hudson sits behind a WAF (curl_cffi browser impersonation, like CSET). Its
listing `article` cards carry the title + `/events/<slug>` link but NO date
("Past Event" / "Event" only) -- the date lives on the detail page as free text
("December 9, 2025"). To avoid fetching a detail page for every card, we
pre-filter cards by title topic (Hudson titles are descriptive) and only fetch
detail pages for on-topic candidates to resolve their date. Hudson HQ is in DC
(1201 Pennsylvania Ave NW) -> dc_curated. The two parse helpers are pure for
offline testing.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime

from ..config import Source
from ..models import Event
from ..normalize import detect_topics
from .base import SourceResult

BASE = "https://www.hudson.org"
TIMEOUT = 30.0
_DATE = re.compile(r"([A-Z][a-z]+ \d{1,2}, \d{4})")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


def parse_hudson_listing(html: str) -> list[dict]:
    """Return candidate stubs {slug, href, title, topics} from the listing.
    Pure + offline-testable; date is resolved later from the detail page."""
    from selectolax.parser import HTMLParser

    tree = HTMLParser(html)
    cands: list[dict] = []
    seen: set[str] = set()
    for card in tree.css("article"):
        a = card.css_first("a[href*='/events/']")
        if a is None:
            continue
        href = (a.attributes.get("href") or "").split("?")[0]
        if "/events/" not in href:
            continue
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        if slug in seen:
            continue
        h = card.css_first("h1,h2,h3,h4")
        title = _clean(h.text() if h else a.text())
        if not title:
            continue
        seen.add(slug)
        cands.append({"slug": slug, "href": href, "title": title,
                      "topics": detect_topics(title)})
    return cands


def parse_hudson_date(detail_html: str) -> str | None:
    """Extract an ISO date from a Hudson detail page ("December 9, 2025")."""
    m = _DATE.search(_TAG.sub(" ", detail_html or ""))
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def _build(cand: dict, start: str) -> Event:
    href = cand["href"]
    return Event(
        id=f"hudson-{cand['slug']}",
        title=cand["title"],
        start=start,
        source="hudson",
        source_url=href if href.startswith("http") else BASE + href,
        organizer="Hudson Institute",
        topics=cand["topics"],
    )


async def fetch_hudson(source: Source) -> SourceResult:
    def _get(url: str) -> tuple[int, str]:
        from curl_cffi import requests as creq

        r = creq.Session(impersonate="chrome").get(url, timeout=TIMEOUT)
        return r.status_code, r.text

    status, html = await asyncio.to_thread(_get, source.url)
    if status != 200:
        return SourceResult(source, [], status, f"HTTP {status}")

    cands = [c for c in parse_hudson_listing(html) if c["topics"]]  # on-topic only
    if not cands:
        return SourceResult(source, [], 200, None)

    async def resolve(cand: dict) -> Event | None:
        url = cand["href"] if cand["href"].startswith("http") else BASE + cand["href"]
        try:
            _, dhtml = await asyncio.to_thread(_get, url)
        except Exception:
            return None
        start = parse_hudson_date(dhtml)
        return _build(cand, start) if start else None

    resolved = await asyncio.gather(*[resolve(c) for c in cands])
    return SourceResult(source, [e for e in resolved if e is not None], 200, None)
