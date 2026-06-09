"""Layer-1 adapter: Luma iCal subscription feeds.

Thin wrapper over the generic iCal fetcher — Luma only differs in that its URL
is built from a calendar id.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import Source
from ..models import Event
from ..normalize import detect_topics
from ..provenance import prov_set
from .base import SourceResult
from .ics import fetch_ics_url

USER_AGENT = "dc-frontier-events/0.4 (+https://lu.ma)"


async def fetch_luma(source: Source) -> SourceResult:
    return await fetch_ics_url(source, source.ics_url, USER_AGENT)


def _local_iso(utc_iso, tzname):
    """'2026-06-10T22:00:00.000Z' + IANA tz -> tz-aware local ISO (or None)."""
    if not utc_iso:
        return None
    dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    if tzname:
        try:
            dt = dt.astimezone(ZoneInfo(tzname))
        except KeyError:
            pass     # unknown tz -> keep UTC rather than drop the event
    return dt.isoformat()


def event_from_json(source: Source, entry: dict) -> Event | None:
    """Luma JSON event (get-items / discover entry) -> normalized Event.
    Returns None for unusable entries (no id/title/start), like parse_ics."""
    ev = entry.get("event") or {}
    eid = ev.get("api_id") or ""
    title = (ev.get("name") or "").strip()
    tzname = ev.get("timezone")
    start = _local_iso(ev.get("start_at"), tzname)
    if not eid or not title or not start:
        return None

    geo = ev.get("geo_address_info") or {}
    address = geo.get("full_address") or geo.get("address") or geo.get("city_state") or ""
    coord = ev.get("coordinate") or {}
    lat, lng = coord.get("latitude"), coord.get("longitude")

    out = Event(
        id=eid,
        title=title,
        start=start,
        end=_local_iso(ev.get("end_at"), tzname),
        tz=tzname,
        source=source.slug,
        source_url=f"https://lu.ma/{ev['url']}" if ev.get("url") else "",
        venue_name=address.split(",")[0].strip() if address else "",
        address=address,
        lat=float(lat) if lat is not None else None,
        lng=float(lng) if lng is not None else None,
        organizer=source.name,
        topics=detect_topics(title),
        raw={"calendar": source.name},
    )
    if ev.get("location_type") == "online":
        out.raw["virtual"] = True
    if address:
        prov_set(out, "location", "structured")
    return out
