"""Emit a unified events.ics (iCalendar) and feed.xml (RSS 2.0).

A "big names only" variant of each is also written, since first-class
attention to watchlisted orgs/people is a core goal.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import date, datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

from icalendar import Calendar
from icalendar import Event as IcsEvent

from .config import SOURCES
from .models import Event

PRODID = "-//dc-frontier-events//EN"
_LAYER = {s.slug: s.layer for s in SOURCES}


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


def _event_dicts(events: list[Event]) -> list[dict]:
    out = []
    for ev in events:
        d = asdict(ev)
        d["layer"] = _LAYER.get(ev.source, 0)
        out.append(d)
    return out


def write_json(events: list[Event], path: str) -> int:
    """Machine-readable export of the full normalized event set."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_event_dicts(events), f, ensure_ascii=False, indent=2, default=str)
    return len(events)


_MAP_TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DC AI & Semiconductor Events — Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
 body{{margin:0;font-family:system-ui,sans-serif}}
 #map{{height:100vh}}
 #hdr{{position:absolute;z-index:1000;top:10px;left:50px;background:#fff;padding:8px 12px;
   border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.3);font-size:13px}}
 .dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px}}
</style></head>
<body>
<div id="hdr"><b>DC AI &amp; Semiconductor Events</b><br>
 {mapped} mapped / {total} total &middot;
 <span class="dot" style="background:#d62728"></span>big name
 <span class="dot" style="background:#9467bd"></span>policy (L2)
 <span class="dot" style="background:#1f77b4"></span>community (L1)</div>
<div id="map"></div>
<script>
var EVENTS = {data};
var map = L.map('map').setView([38.9, -77.03], 11);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
  {{maxZoom:19, attribution:'&copy; OpenStreetMap'}}).addTo(map);
EVENTS.forEach(function(e){{
  var color = e.is_big_name ? '#d62728' : (e.layer===2 ? '#9467bd' : '#1f77b4');
  var p = L.circleMarker([e.lat, e.lng], {{radius:7, color:color, fillColor:color,
    fillOpacity:0.8, weight:1}}).addTo(map);
  var link = e.source_url ? '<br><a href="'+e.source_url+'" target="_blank">details</a>' : '';
  p.bindPopup('<b>'+e.title+'</b><br>'+(e.start||'').slice(0,10)+'<br>'+
    (e.address||'')+link);
}});
</script></body></html>
"""


def write_map(events: list[Event], path: str) -> int:
    """Static Leaflet map of every event that carries GEO coordinates."""
    geo = [e for e in events if e.lat is not None and e.lng is not None]
    payload = json.dumps(
        [{"title": e.title, "start": e.start, "lat": e.lat, "lng": e.lng,
          "address": e.address, "source_url": e.source_url,
          "is_big_name": e.is_big_name, "layer": _LAYER.get(e.source, 0)} for e in geo],
        ensure_ascii=False,
    ).replace("</", "<\\/")  # safe to embed inside <script>
    html = _MAP_TEMPLATE.format(data=payload, mapped=len(geo), total=len(events))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return len(geo)
