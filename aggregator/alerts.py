"""Alerting: surface events that are new since the last run, with first-class
attention to newly-announced big-name / watchlisted events (GOAL: "alerts when a
watchlisted org/person is announced"). Pure render; the pipeline supplies the
new-since-last-run diff from the persistent store.
"""

from __future__ import annotations

from .config import DC_BBOX, SOURCES
from .models import Event

_NAME = {s.slug: s.name for s in SOURCES}


def _line(e: Event) -> str:
    src = _NAME.get(e.source, e.source)
    link = f" — {e.source_url}" if e.source_url else ""
    star = "⭐ " if e.is_big_name else ""
    topics = ", ".join(t for t in e.topics if not t.startswith("big:"))
    tail = f" · {topics}" if topics else ""
    return f"- {star}**{(e.start or '')[:10]}** · {e.title} · {src}{tail}{link}"


def _big_tags(e: Event) -> str:
    """The matched watchlist names ('big:X' tags) as a readable list."""
    return ", ".join(t[4:] for t in e.topics if t.startswith("big:"))


def _in_person_dc(e: Event) -> bool:
    """True iff the event has real coordinates inside the DC bounding box (a
    physical, in-town event -- not a virtual/geo-less one)."""
    if e.lat is None or e.lng is None:
        return False
    b = DC_BBOX
    return b["lat_min"] <= e.lat <= b["lat_max"] and b["lng_min"] <= e.lng <= b["lng_max"]


def big_names_in_dc(events: list[Event], today_iso: str) -> list[Event]:
    """The highest-signal case: a watchlisted org/person physically appearing at
    an upcoming, in-DC, in-person event (Dario/Sam/Jensen actually in town). This
    is independent of new-since-last-run -- it stays loud while the event is
    upcoming. Sorted soonest-first."""
    hits = [e for e in events
            if e.is_big_name and _in_person_dc(e) and (e.start or "")[:10] >= today_iso]
    hits.sort(key=lambda e: e.start or "")
    return hits


def _dc_line(e: Event) -> str:
    src = _NAME.get(e.source, e.source)
    link = f" — {e.source_url}" if e.source_url else ""
    who = _big_tags(e)
    who_s = f" — 🎯 {who}" if who else ""
    venue = f" @ {e.venue_name}" if e.venue_name else ""
    return f"- **{(e.start or '')[:10]}** · {e.title}{who_s} · {src}{venue}{link}"


def build_alerts(new_events: list[Event], new_big: list[Event],
                 today_iso: str, first_run: bool = False,
                 deadlines_soon: list | None = None,
                 open_apps: list | None = None,
                 big_in_dc: list[Event] | None = None) -> str:
    out = ["# DC AI & Semiconductor — Alerts", f"_Generated {today_iso}_", ""]
    if first_run:
        out += [f"_First run — baseline established ({len(new_events)} events, "
                f"{len(new_big)} big-name). Future runs itemize only newly-added events._", ""]

    # Marquee names physically in DC -- the loudest signal, shown first. Stays up
    # while the event is upcoming (not gated on new-since-last-run).
    big_in_dc = big_in_dc or []
    if big_in_dc:
        out.append(f"## 🚨 Big names in DC — in person ({len(big_in_dc)})")
        out += [_dc_line(e) for e in big_in_dc]
        out.append("")

    # Application deadlines closing soon -- first, because missing one is costly.
    # deadlines_soon is a list of (Credential, days_until), soonest first.
    deadlines_soon = deadlines_soon or []
    out.append(f"## ⏳ Application deadlines closing soon ({len(deadlines_soon)})")
    if deadlines_soon:
        for c, d in deadlines_soon:
            urgency = "‼️" if d <= 14 else "⏰"
            out.append(f"- {urgency} **{c.deadline}** ({d} days) — {c.name} · "
                       f"{c.provider} — {c.url}")
    else:
        out.append("_None within the alert window._")
    out.append("")

    # Applications open now (no posted date) -- actionable even without a deadline.
    open_apps = open_apps or []
    if open_apps:
        out.append(f"## ✅ Applications open now ({len(open_apps)})")
        for c in open_apps:
            out.append(f"- **{c.name}** · {c.provider} — apply now — {c.scrape_url}")
        out.append("")

    out.append(f"## 🔔 New big-name events ({len(new_big)})")
    if new_big:
        out += [_line(e) for e in sorted(new_big, key=lambda x: x.start or "")]
    else:
        out.append("_None._")

    # Itemize ALL newly-added events (not just big names) so a subscriber sees
    # exactly what appeared since the last run. On the first/baseline run the
    # full set is everything, so we suppress the (huge) list and just note it.
    out += ["", f"## 🆕 New events since last run ({len(new_events)})"]
    if first_run:
        out.append("_(baseline run — full list suppressed; itemized on future runs)_")
    elif new_events:
        out += [_line(e) for e in sorted(new_events, key=lambda x: x.start or "")]
    else:
        out.append("_None._")
    return "\n".join(out) + "\n"
