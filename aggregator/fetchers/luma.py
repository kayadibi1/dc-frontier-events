"""Layer-1 adapter: Luma iCal subscription feeds (async httpx + icalendar)."""

from __future__ import annotations

import httpx

from ..config import Source
from ..normalize import parse_ics
from .base import SourceResult

USER_AGENT = "dc-frontier-events/0.2 (+https://lu.ma)"
TIMEOUT = 30.0


async def fetch_luma(source: Source) -> SourceResult:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/calendar, */*"}
    async with httpx.AsyncClient(
        headers=headers, timeout=TIMEOUT, follow_redirects=True
    ) as client:
        r = await client.get(source.ics_url)
        if r.status_code != 200:
            return SourceResult(source, [], r.status_code, f"HTTP {r.status_code}")
        if "BEGIN:VEVENT" not in r.text:
            return SourceResult(source, [], 200, None)  # fetched fine, just empty
        return SourceResult(source, parse_ics(source, r.text), 200, None)
