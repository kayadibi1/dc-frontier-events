"""Relevance filter + big-name flagging.

Keep an event iff:
    (DC-metro  OR  virtual-from-a-DC-curated-source)
  AND
    (on-topic  OR  matches the big-name watchlist).

Sets `is_big_name` and records matched big-name signals as `big:<Name>` tags
in `topics` (a real topic is still required separately unless is_big_name).
"""

from __future__ import annotations

import re

from .config import (
    BIG_NAME_PATTERNS,
    DC_BBOX,
    DC_TEXT_PATTERN,
    SOURCES,
    VIRTUAL_PATTERN,
)
from .models import Event

_DC_TEXT = re.compile(DC_TEXT_PATTERN, re.I)
_VIRTUAL = re.compile(VIRTUAL_PATTERN, re.I)
_BIG = {n: re.compile(p, re.I) for n, p in BIG_NAME_PATTERNS.items()}
_DC_CURATED = {s.slug for s in SOURCES if s.dc_curated}


def _geo_in_dc(ev: Event) -> bool:
    if ev.lat is None or ev.lng is None:
        return False
    b = DC_BBOX
    return b["lat_min"] <= ev.lat <= b["lat_max"] and b["lng_min"] <= ev.lng <= b["lng_max"]


def _text_blob(ev: Event) -> str:
    return " ".join([ev.title, ev.description, ev.address, ev.organizer,
                     ev.raw.get("location", "")])


def _big_names(ev: Event) -> list[str]:
    blob = _text_blob(ev)
    return [n for n, rx in _BIG.items() if rx.search(blob)]


def is_dc_relevant(ev: Event) -> bool:
    if _geo_in_dc(ev):
        return True
    blob = _text_blob(ev)
    virtual = bool(_VIRTUAL.search(blob))
    has_geo = ev.lat is not None and ev.lng is not None
    # An in-person event with real coordinates outside DC is not a DC event,
    # regardless of incidental text (e.g. a Hampton Roads, VA address matching
    # ", va"). GEO is authoritative when present and the event is physical.
    if has_geo and not virtual:
        return False
    # Virtual or geo-less: fall back to explicit DC text, or trust a genuinely
    # DC-scoped (dc_curated) calendar's curation.
    if _DC_TEXT.search(blob):
        return True
    if ev.source in _DC_CURATED:
        return True
    return False


def apply_filters(events: list[Event]) -> tuple[list[Event], dict]:
    kept: list[Event] = []
    stats = {"dropped_location": 0, "dropped_topic": 0, "big_name": 0}
    for ev in events:
        names = _big_names(ev)
        if names:
            ev.is_big_name = True
            for n in names:
                tag = f"big:{n}"
                if tag not in ev.topics:
                    ev.topics.append(tag)

        if not is_dc_relevant(ev):
            stats["dropped_location"] += 1
            continue

        has_real_topic = any(not t.startswith("big:") for t in ev.topics)
        if not (has_real_topic or ev.is_big_name):
            stats["dropped_topic"] += 1
            continue

        if ev.is_big_name:
            stats["big_name"] += 1
        kept.append(ev)
    return kept, stats
