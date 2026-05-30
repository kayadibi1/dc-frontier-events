"""Auto-fetch application deadlines for credential programs.

On each run, fetch each program's page and look for a date adjacent to a deadline
keyword ("apply by", "applications close", "deadline", "due"). CRITICAL honesty
rules:
  - only accept a date that is in the FUTURE relative to today (rejects expired /
    archived cycle dates like a past "apply by January 20, 2025");
  - if nothing valid is found, leave the program's deadline as-is (status note).
This makes the deadline tracker self-updating instead of hand-wired, while never
inventing or surfacing a stale date.

extract_deadline() is pure (html + today -> iso date | None) so it is unit-tested
offline; fetch_deadlines() does the network and is best-effort (failures skip).
"""

from __future__ import annotations

import asyncio
import re
from datetime import date

import httpx

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 25.0

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
# A deadline keyword followed (within ~60 chars) by a date, OR a date followed by
# such a keyword. Keyword set is deliberately specific to APPLICATION deadlines.
_KEYWORD = (r"appl(?:y|ication[s]?)\s+(?:by|close[sd]?|due|deadline|open[s]? until)|"
            r"\bdeadline\b|\bdue\s+(?:by|date)\b|submissions?\s+(?:close|due)|"
            r"close[sd]?\s+on|register\s+by")
_MONTH = (r"(?:January|February|March|April|May|June|July|August|September|"
          r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)")
_DATE = rf"{_MONTH}\.?\s+\d{{1,2}},?\s+\d{{4}}|\d{{1,2}}/\d{{1,2}}/\d{{4}}"

_KW_THEN_DATE = re.compile(rf"(?:{_KEYWORD})[^.\n]{{0,60}}?({_DATE})", re.I)
_DATE_THEN_KW = re.compile(rf"({_DATE})[^.\n]{{0,40}}?(?:{_KEYWORD})", re.I)

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
_ABBR = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
         "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}


def _to_iso(raw: str) -> str | None:
    raw = raw.strip().rstrip(".,")
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if m:  # US M/D/Y
        mo, da, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.match(rf"({_MONTH})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})", raw, re.I)
        if not m:
            return None
        name = m.group(1).lower().rstrip(".")
        mo = _MONTHS.get(name) or _ABBR.get(name)
        da, yr = int(m.group(2)), int(m.group(3))
    if not mo or not (1 <= da <= 31):
        return None
    try:
        return date(yr, mo, da).isoformat()
    except ValueError:
        return None


def extract_deadline(html: str, today_iso: str) -> str | None:
    """Return the soonest FUTURE deadline date (ISO) found near a deadline
    keyword, or None. Past/expired dates are rejected."""
    text = _WS.sub(" ", _TAG.sub(" ", html or ""))
    cands: set[str] = set()
    for rx in (_KW_THEN_DATE, _DATE_THEN_KW):
        for m in rx.finditer(text):
            iso = _to_iso(m.group(1))
            if iso:
                cands.add(iso)
    future = sorted(d for d in cands if d >= today_iso)
    return future[0] if future else None


async def _fetch_one(client: httpx.AsyncClient, url: str, today_iso: str) -> str | None:
    try:
        r = await client.get(url)
        if r.status_code != 200:
            return None
        return extract_deadline(r.text, today_iso)
    except Exception:
        return None


async def fetch_deadlines(urls: list[str], today_iso: str) -> dict[str, str]:
    """Map url -> future deadline ISO date, for urls where one was found.
    Best-effort: unreachable pages / no-date pages are simply absent."""
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"}
    async with httpx.AsyncClient(headers=headers, timeout=TIMEOUT,
                                 follow_redirects=True) as client:
        results = await asyncio.gather(
            *[_fetch_one(client, u, today_iso) for u in urls])
    return {u: d for u, d in zip(urls, results) if d}
