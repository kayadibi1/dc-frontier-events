"""Per-source fetch adapters.

Each adapter takes a Source and returns a SourceResult carrying already-normalized
Event objects plus status/error, so the rest of the pipeline is format-agnostic.
A single source's failure is captured as an error, never an exception that aborts
the whole run.
"""

from __future__ import annotations

import asyncio

from ..config import Source
from .base import SourceResult
from .csis import fetch_csis
from .cset import fetch_cset
from .ics import fetch_ics
from .luma import fetch_luma

ADAPTERS = {
    "luma": fetch_luma,
    "ics": fetch_ics,
    "cset": fetch_cset,
    "csis": fetch_csis,
}


async def gather_all(sources: list[Source]) -> list[SourceResult]:
    async def one(src: Source) -> SourceResult:
        fn = ADAPTERS.get(src.kind)
        if fn is None:
            return SourceResult(src, [], None, f"no adapter for kind={src.kind!r}")
        try:
            return await fn(src)
        except Exception as e:  # adapter crash must not kill the run
            return SourceResult(src, [], None, repr(e))

    return list(await asyncio.gather(*[one(s) for s in sources]))
