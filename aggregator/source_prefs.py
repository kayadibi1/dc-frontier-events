"""Source-origin preference helpers for calendars and subscriber digests.

An empty preference means "all sources" for backwards compatibility with every
existing subscriber and the public all-events feeds.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from .config import SOURCES
from .models import Event

ALL_SOURCE_SLUGS = tuple(s.slug for s in SOURCES)
VALID_SOURCE_SLUGS = set(ALL_SOURCE_SLUGS)
SOURCE_NAMES = {s.slug: s.name for s in SOURCES}


def normalize_sources(values) -> tuple[str, ...]:
    """Return known source slugs in config order, de-duped.

    Accepts a comma-separated string or an iterable of strings. Unknown slugs are
    ignored so form tampering cannot create surprising filters.
    """
    if values is None:
        return ()
    if isinstance(values, str):
        parts = values.replace(";", ",").split(",")
    else:
        parts = []
        for value in values:
            if isinstance(value, str):
                parts.extend(value.replace(";", ",").split(","))
    wanted = {p.strip() for p in parts if p and p.strip() in VALID_SOURCE_SLUGS}
    return tuple(slug for slug in ALL_SOURCE_SLUGS if slug in wanted)


def encode_sources(values) -> str:
    """SQLite-friendly source preference string. Blank means all sources."""
    slugs = normalize_sources(values)
    if not slugs or len(slugs) == len(ALL_SOURCE_SLUGS):
        return ""
    return ",".join(slugs)


def decode_sources(value: str | None) -> tuple[str, ...]:
    return normalize_sources(value or "")


def source_query(values) -> str:
    """Query-string fragment for a source-filtered public calendar URL."""
    encoded = encode_sources(values)
    return f"sources={quote_plus(encoded)}" if encoded else ""


def filter_events_by_sources(events: list[Event], sources) -> list[Event]:
    """Filter by event origin source.

    Dedupe records cross-posted origins in raw.also_sources; a user who selected
    any origin that supplied the event should still see it.
    """
    wanted = set(normalize_sources(sources))
    if not wanted:
        return list(events)
    out: list[Event] = []
    for ev in events:
        origins = {ev.source}
        also = ev.raw.get("also_sources", []) if isinstance(ev.raw, dict) else []
        if isinstance(also, list):
            origins.update(s for s in also if isinstance(s, str))
        if origins & wanted:
            out.append(ev)
    return out


def source_label(values) -> str:
    slugs = normalize_sources(values)
    if not slugs:
        return "all sources"
    if len(slugs) == 1:
        return SOURCE_NAMES.get(slugs[0], slugs[0])
    return f"{len(slugs)} sources"
