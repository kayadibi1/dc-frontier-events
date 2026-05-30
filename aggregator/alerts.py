"""Alerting: surface events that are new since the last run, with first-class
attention to newly-announced big-name / watchlisted events (GOAL: "alerts when a
watchlisted org/person is announced"). Pure render; the pipeline supplies the
new-since-last-run diff from the persistent store.
"""

from __future__ import annotations

from .config import SOURCES
from .models import Event

_NAME = {s.slug: s.name for s in SOURCES}


def _line(e: Event) -> str:
    src = _NAME.get(e.source, e.source)
    link = f" — {e.source_url}" if e.source_url else ""
    star = "⭐ " if e.is_big_name else ""
    topics = ", ".join(t for t in e.topics if not t.startswith("big:"))
    tail = f" · {topics}" if topics else ""
    return f"- {star}**{(e.start or '')[:10]}** · {e.title} · {src}{tail}{link}"


def build_alerts(new_events: list[Event], new_big: list[Event],
                 today_iso: str, first_run: bool = False,
                 deadlines_soon: list | None = None) -> str:
    out = ["# DC AI & Semiconductor — Alerts", f"_Generated {today_iso}_", ""]
    if first_run:
        out += [f"_First run — baseline established ({len(new_events)} events, "
                f"{len(new_big)} big-name). Future runs itemize only newly-added events._", ""]

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
