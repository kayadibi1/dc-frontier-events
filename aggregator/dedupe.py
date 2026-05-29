"""Collapse duplicate events.

Two passes:
  1. exact: same cleaned UID -- the same Luma event cross-listed on several
     calendars (e.g. it shows on both DC2 and aic-washington).
  2. fuzzy: same start-day + near-identical normalized title (SequenceMatcher)
     -- catches cross-platform dupes (Luma vs Meetup vs Eventbrite) that carry
     different UIDs.
The earliest-seen event wins; merged sources are recorded for transparency.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import Event

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
FUZZY_THRESHOLD = 0.88


def _norm_title(t: str) -> str:
    return _NON_ALNUM.sub(" ", t.lower()).strip()


def _day(iso: str) -> str:
    return (iso or "")[:10]


def _merge_source(canonical: Event, other: Event) -> None:
    if other.source != canonical.source:
        also = canonical.raw.setdefault("also_sources", [])
        if other.source not in also:
            also.append(other.source)


def dedupe(events: list[Event]) -> tuple[list[Event], int]:
    # Pass 1: exact id.
    by_id: dict[str, Event] = {}
    for ev in events:
        if ev.id not in by_id:
            by_id[ev.id] = ev
        else:
            _merge_source(by_id[ev.id], ev)
    stage1 = list(by_id.values())

    # Pass 2: fuzzy title within the same day.
    kept: list[Event] = []
    buckets: dict[str, list[Event]] = {}
    for ev in stage1:
        day = _day(ev.start)
        nt = _norm_title(ev.title)
        match = None
        for other in buckets.get(day, []):
            if SequenceMatcher(None, nt, _norm_title(other.title)).ratio() >= FUZZY_THRESHOLD:
                match = other
                break
        if match is None:
            buckets.setdefault(day, []).append(ev)
            kept.append(ev)
        else:
            _merge_source(match, ev)

    removed = len(events) - len(kept)
    return kept, removed
