"""Weekly digest: a human-readable markdown summary of the top-ranked upcoming
events (and any big-name events), built on the relevance ranking. Foundation for
the GOAL's weekly emailer. Pure function, testable.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from .config import SOURCES
from .models import Event
from .rank import score_event, top_upcoming

_NAME = {s.slug: s.name for s in SOURCES}


def _h(s: str) -> str:
    return escape(s or "", {'"': "&quot;"})


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


_HTML_STYLE = (
    "body{font-family:system-ui,Arial,sans-serif;max-width:680px;margin:auto;color:#222;"
    "padding:16px}h1{font-size:20px;margin-bottom:2px}h2{font-size:15px;border-bottom:1px "
    "solid #eee;padding-bottom:4px;margin-top:24px}ul{list-style:none;padding:0}"
    "li{padding:8px 0;border-bottom:1px solid #f2f2f2}small{color:#666}"
    ".meta{color:#888;font-size:13px}.star{color:#d62728}"
)


def _html_item(ev: Event, today_iso: str) -> str:
    topics = ", ".join(_real_topics(ev)) or "—"
    star = '<span class="star">★</span> ' if ev.is_big_name else ""
    link = f' · <a href="{_h(ev.source_url)}">details</a>' if ev.source_url else ""
    return (f"<li><b>{(ev.start or '')[:10]}</b> — {star}{_h(ev.title)}<br>"
            f"<small>{_h(_NAME.get(ev.source, ev.source))} · {_h(_loc(ev))} · "
            f"{_h(topics)} · score {score_event(ev, today_iso)}{link}</small></li>")


def render_html(events: list[Event], today_iso: str, top_n: int = 15) -> str:
    """HTML rendering of the digest (web + email body). Self-contained, inline <style>."""
    upcoming = [e for e in events if (e.start or "")[:10] >= today_iso]
    top = top_upcoming(events, today_iso, n=top_n)
    bigs = [e for e in top if e.is_big_name]
    big_html = "".join(_html_item(e, today_iso) for e in bigs) or \
        "<li><small>None scheduled in range — DC big names cluster at CSET/CSIS.</small></li>"
    top_html = "".join(_html_item(e, today_iso) for e in top) or \
        "<li><small>No upcoming events in range.</small></li>"
    return (
        f"<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>DC AI &amp; Semiconductor — Weekly Digest</title><style>{_HTML_STYLE}</style></head>"
        f"<body><h1>DC AI &amp; Semiconductor — Weekly Digest</h1>"
        f"<p class=\"meta\">{today_iso} · {len(upcoming)} upcoming event(s) across "
        f"{len({e.source for e in upcoming})} source(s)</p>"
        f"<h2>⭐ Big names ({len(bigs)})</h2><ul>{big_html}</ul>"
        f"<h2>Top upcoming ({len(top)})</h2><ul>{top_html}</ul>"
        f"</body></html>"
    )
