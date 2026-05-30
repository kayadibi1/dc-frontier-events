"""Speaker enrichment for Layer-2 detail pages.

extract_speakers parses both structured speaker markup (CSIS:
[class*=speaker]/[class*=participant]) and prose ("featuring X and Y, moderated
by Z" -- CSET). enrich_layer2 fetches each Layer-2 event's detail page and sets
Event.speakers (best-effort; failures leave speakers empty).
"""

from __future__ import annotations

import asyncio
import re

import httpx
from selectolax.parser import HTMLParser

from .models import Event

# A person name: 2-4 capitalized words (allowing internal hyphen/period/').
_NAME = re.compile(r"\b([A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){1,3})\b")
# Words that look capitalized but are not names (cut false positives).
_STOP = {"Register Now", "Read More", "Learn More", "Add To", "Google Calendar",
         "Watch Now", "Event Page", "Privacy Policy", "United States",
         "New York", "Washington Dc", "Add To Calendar"}
_INTRO = re.compile(r"(?:featuring|fireside chat with|joined by|with|moderated by|"
                    r"keynote by|in conversation with|speakers?:)\s+(.+?)(?:\.|\n|$)", re.I)

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _looks_like_name(s: str) -> bool:
    s = s.strip()
    if s in _STOP or any(ch.isdigit() for ch in s):
        return False
    parts = s.split()
    return 2 <= len(parts) <= 4 and all(p[:1].isupper() for p in parts)


def extract_speakers(html: str) -> list[str]:
    tree = HTMLParser(html)
    found: list[str] = []

    # 1) structured nodes
    for node in tree.css("[class*='speaker'], [class*='participant'], [class*='panelist']"):
        name_node = node.css_first("[class*='name']") or node
        cand = _clean(name_node.text())
        if _looks_like_name(cand):
            found.append(cand)

    # 2) prose fallback ("featuring A and B, moderated by C")
    if not found:
        body = tree.body.text(separator=" ") if tree.body else (tree.text() or "")
        for m in _INTRO.finditer(body):
            chunk = m.group(1)
            for piece in re.split(r",|\band\b|&", chunk):
                for nm in _NAME.findall(piece):
                    if _looks_like_name(nm):
                        found.append(nm)

    # dedupe preserving order
    seen, out = set(), []
    for n in found:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


async def default_fetch(url: str, source_kind: str) -> str:
    """Fetch a detail page: curl_cffi (browser TLS) for cset (WAF), httpx else."""
    if source_kind == "cset":
        def _go():
            from curl_cffi import requests as creq
            return creq.Session(impersonate="chrome").get(url, timeout=30).text
        return await asyncio.to_thread(_go)
    async with httpx.AsyncClient(headers={"User-Agent": _UA}, timeout=30,
                                 follow_redirects=True) as c:
        r = await c.get(url)
        return r.text if r.status_code == 200 else ""


async def enrich_layer2(events: list[Event], layer_by_source: dict[str, int],
                        fetch) -> int:
    """For each Layer-2 event with a source_url, fetch its detail page via
    `fetch(url, source_kind)` and set ev.speakers. Best-effort: a failed fetch
    leaves speakers empty. `fetch` is async and returns HTML (or '' on failure).
    Returns the number of events enriched with >=1 speaker."""
    targets = [e for e in events
               if layer_by_source.get(e.source, 0) == 2 and e.source_url]

    async def one(ev: Event) -> int:
        try:
            html = await fetch(ev.source_url, ev.source)
        except Exception:
            return 0
        ev.speakers = extract_speakers(html or "")
        return 1 if ev.speakers else 0

    results = await asyncio.gather(*[one(e) for e in targets])
    return sum(results)
