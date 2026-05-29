"""Emit a unified events.ics (iCalendar) and feed.xml (RSS 2.0).

A "big names only" variant of each is also written, since first-class
attention to watchlisted orgs/people is a core goal.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

from icalendar import Calendar
from icalendar import Event as IcsEvent

from .models import Event

PRODID = "-//dc-frontier-events//EN"


def _parse_dt(iso: str | None):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        try:
            return date.fromisoformat(iso[:10])
        except ValueError:
            return None


def filter_upcoming(events: list[Event], today_iso: str) -> list[Event]:
    """Events whose start date is today or later. ISO date strings compare
    chronologically as plain strings, so this works on both date and datetime starts."""
    return [e for e in events if (e.start or "")[:10] >= today_iso]


def _to_utc(dt):
    """Normalize an aware datetime to UTC so iCal emits an unambiguous '...Z'.
    icalendar serializes a fixed-offset tz as an invalid TZID (e.g. "UTC-04:00")
    with no VTIMEZONE; converting to UTC avoids that. Naive/date values pass through.
    """
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    return dt


def _star(ev: Event) -> str:
    return "★ " if ev.is_big_name else ""


def write_ics(events: list[Event], path: str) -> int:
    cal = Calendar()
    cal.add("prodid", PRODID)
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "DC AI & Semiconductor Events")
    now = datetime.now(timezone.utc)
    n = 0
    for ev in events:
        dt = _parse_dt(ev.start)
        if dt is None:
            continue
        ie = IcsEvent()
        ie.add("uid", ev.id)
        ie.add("dtstamp", now)
        ie.add("summary", _star(ev) + ev.title)
        ie.add("dtstart", _to_utc(dt))
        end = _parse_dt(ev.end)
        if end is not None:
            ie.add("dtend", _to_utc(end))
        if ev.address:
            ie.add("location", ev.address)
        if ev.lat is not None and ev.lng is not None:
            ie.add("geo", (ev.lat, ev.lng))
        if ev.topics:
            ie.add("categories", ev.topics)
        desc = ev.description
        if ev.source_url:
            ie.add("url", ev.source_url)
            desc = f"{desc}\n\nSource: {ev.source_url}".strip()
        ie.add("description", desc)
        cal.add_component(ie)
        n += 1
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(cal.to_ical())
    return n


def _rfc822(iso: str | None) -> str:
    dt = _parse_dt(iso)
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    elif isinstance(dt, date):
        dt = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
    else:
        dt = datetime.now(timezone.utc)
    return format_datetime(dt)


def write_rss(events: list[Event], path: str,
              title: str = "DC AI & Semiconductor Events") -> int:
    items = []
    for ev in events:
        topics = ", ".join(ev.topics)
        big = "★ BIG NAME -- " if ev.is_big_name else ""
        body = "\n".join(p for p in [ev.address, ev.description,
                                     f"Topics: {topics}" if topics else ""] if p)
        items.append(
            "<item>"
            f"<title>{escape(_star(ev) + ev.title)}</title>"
            f"<link>{escape(ev.source_url or '')}</link>"
            f'<guid isPermaLink="false">{escape(ev.id)}</guid>'
            f"<pubDate>{_rfc822(ev.start)}</pubDate>"
            f"<description>{escape(big + body)}</description>"
            "</item>"
        )
    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        f"<title>{escape(title)}</title>"
        "<link>https://lu.ma/DC2</link>"
        f"<description>{escape(title)} -- aggregated, deduped, filtered.</description>"
        + "".join(items)
        + "</channel></rss>"
    )
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(rss)
    return len(items)
