"""Alerting: surface events that are new since the last run, with first-class
attention to newly-announced big-name / watchlisted events (GOAL: "alerts when a
watchlisted org/person is announced"). Pure render; the pipeline supplies the
new-since-last-run diff from the persistent store.
"""

from __future__ import annotations

from .config import SOURCES
from .models import Event

_NAME = {s.slug: s.name for s in SOURCES}


def build_alerts(new_events: list[Event], new_big: list[Event],
                 today_iso: str, first_run: bool = False) -> str:
    out = ["# DC AI & Semiconductor — Alerts", f"_Generated {today_iso}_", ""]
    if first_run:
        out += [f"_First run — baseline established ({len(new_events)} events, "
                f"{len(new_big)} big-name). Future runs alert only on newly-added events._", ""]

    out.append(f"## 🔔 New big-name events ({len(new_big)})")
    if new_big:
        for e in sorted(new_big, key=lambda x: x.start or ""):
            src = _NAME.get(e.source, e.source)
            link = f" — {e.source_url}" if e.source_url else ""
            out.append(f"- **{(e.start or '')[:10]}** · {e.title} · {src}{link}")
    else:
        out.append("_None._")

    out += ["", f"## New events since last run: {len(new_events)}"]
    return "\n".join(out) + "\n"
