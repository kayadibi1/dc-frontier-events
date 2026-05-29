"""Weekly digest: a human-readable markdown summary of the top-ranked upcoming
events (and any big-name events), built on the relevance ranking. Foundation for
the GOAL's weekly emailer. Pure function, testable.
"""

from __future__ import annotations

from .config import SOURCES
from .models import Event
from .rank import score_event, top_upcoming

_NAME = {s.slug: s.name for s in SOURCES}


def _loc(ev: Event) -> str:
    if ev.address:
        return ev.address
    if ev.raw.get("virtual"):
        return "virtual"
    return "TBD"


def _real_topics(ev: Event) -> list[str]:
    return [t for t in ev.topics if not t.startswith("big:")]


def _line(ev: Event, today_iso: str) -> str:
    topics = ", ".join(_real_topics(ev)) or "—"
    src = _NAME.get(ev.source, ev.source)
    link = f" · [details]({ev.source_url})" if ev.source_url else ""
    star = "⭐ " if ev.is_big_name else ""
    return (f"**{(ev.start or '')[:10]}** — {star}{ev.title}  \n"
            f"  {src} · {_loc(ev)} · {topics} · score {score_event(ev, today_iso)}{link}")


def build_digest(events: list[Event], today_iso: str, top_n: int = 15) -> str:
    upcoming_all = [e for e in events if (e.start or "")[:10] >= today_iso]
    top = top_upcoming(events, today_iso, n=top_n)
    bigs = [e for e in top if e.is_big_name]

    out = [
        "# DC AI & Semiconductor — Weekly Digest",
        f"_Generated {today_iso} · {len(upcoming_all)} upcoming event(s) across "
        f"{len({e.source for e in upcoming_all})} source(s)._",
        "",
        "## ⭐ Big names",
    ]
    if bigs:
        out += [f"- {_line(e, today_iso)}" for e in bigs]
    else:
        out.append("_None scheduled in range — DC big names cluster at Layer-2 "
                   "venues (CSET/CSIS); watch this section._")

    out += ["", f"## Top upcoming (ranked, showing {len(top)})"]
    if top:
        out += [f"{i}. {_line(e, today_iso)}" for i, e in enumerate(top, 1)]
    else:
        out.append("_No upcoming events in range._")
    out.append("")
    return "\n".join(out) + "\n"
