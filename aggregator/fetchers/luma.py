"""Layer-1 adapter: Luma iCal subscription feeds.

Thin wrapper over the generic iCal fetcher — Luma only differs in that its URL
is built from a calendar id.
"""

from __future__ import annotations

from ..config import Source
from .base import SourceResult
from .ics import fetch_ics_url

USER_AGENT = "dc-frontier-events/0.4 (+https://lu.ma)"


async def fetch_luma(source: Source) -> SourceResult:
    return await fetch_ics_url(source, source.ics_url, USER_AGENT)
