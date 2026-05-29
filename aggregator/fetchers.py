"""Async fetchers. Phase 1: Luma iCal subscription endpoints.

Each fetch returns the raw .ics text (parsing happens in normalize) plus the
HTTP status, so the pipeline can quarantine empty/failed sources with concrete
diagnostics instead of crashing or silently dropping them.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from .config import Source

USER_AGENT = "dc-frontier-events/0.1 (+https://lu.ma)"
TIMEOUT = 30.0


@dataclass
class FetchResult:
    source: Source
    ics_text: str | None
    status: int | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.ics_text is not None and "BEGIN:VEVENT" in self.ics_text


async def _fetch_one(client: httpx.AsyncClient, source: Source) -> FetchResult:
    try:
        r = await client.get(source.ics_url)
        if r.status_code != 200:
            return FetchResult(source, None, r.status_code, f"HTTP {r.status_code}")
        return FetchResult(source, r.text, 200)
    except Exception as e:  # a single source's network error must not kill the run
        return FetchResult(source, None, None, repr(e))


async def fetch_all(sources: list[Source]) -> list[FetchResult]:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/calendar, */*"}
    async with httpx.AsyncClient(
        headers=headers, timeout=TIMEOUT, follow_redirects=True
    ) as client:
        return list(await asyncio.gather(*[_fetch_one(client, s) for s in sources]))
