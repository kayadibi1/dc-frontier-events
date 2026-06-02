"""Two-phase validation gate. Prefer omitting/downgrading a field to emitting a
wrong value. `validate_pre_filter` cleans fields the relevance filter consumes (so
it runs BEFORE apply_filters, which is not idempotent). `validate_post_geocode`
does coordinate cross-checks AFTER geocode. Each returns (clean, dropped),
dropped = list of (event_id, field, reason). `today_iso` is injected (never
wall-clock) for deterministic tests / --today runs.
"""
from __future__ import annotations

from datetime import date, datetime

from .enrich import _looks_like_name
from .models import Event

DATE_WINDOW_YEARS = 3
MAX_SPEAKERS = 12


def _date_of(start: str | None):
    if not start:
        return None
    try:
        return date.fromisoformat(start[:10])
    except ValueError:
        return None


def _is_timed(start: str | None) -> bool:
    return bool(start) and "T" in start


def _tzinfo_of(start: str | None):
    try:
        return datetime.fromisoformat(start).tzinfo if start else None
    except ValueError:
        return None


def validate_pre_filter(events: list[Event], today_iso: str) -> tuple[list[Event], list]:
    today = date.fromisoformat(today_iso)
    lo = date(today.year - DATE_WINDOW_YEARS, 1, 1)
    hi = date(today.year + DATE_WINDOW_YEARS, 12, 31)
    clean: list[Event] = []
    dropped: list = []
    for ev in events:
        d = _date_of(ev.start)
        if d is None or not (lo <= d <= hi):
            dropped.append((ev.id, "date", f"implausible:{ev.start}"))
            continue
        if _is_timed(ev.start) and _tzinfo_of(ev.start) is None:
            dropped.append((ev.id, "time", "timed-no-tz"))
            ev.start = ev.start[:10]
            if ev.end:
                ev.end = ev.end[:10]
            ev.tz = None
        if ev.speakers:
            cleaned = [s for s in ev.speakers if _looks_like_name(s)]
            if len(cleaned) > MAX_SPEAKERS:
                dropped.append((ev.id, "speakers", "over-limit"))
                cleaned = []
            elif len(cleaned) != len(ev.speakers):
                dropped.append((ev.id, "speakers", "junk-removed"))
            ev.speakers = cleaned
        # A pure-virtual event must not carry a physical-venue (HQ) fallback.
        # No generic junk-address nulling here -- that would erase valid ZIP-less
        # venues (e.g. "Marvin Center, Washington, DC"); handled, geocode-informed,
        # in validate_post_geocode.
        if ev.raw.get("virtual") and ev.address:
            dropped.append((ev.id, "address", "virtual-cleared"))
            ev.address = ""
        clean.append(ev)
    return clean, dropped
