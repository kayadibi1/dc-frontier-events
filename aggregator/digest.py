"""Weekly digest: a human-readable markdown summary of the top-ranked upcoming
events (and any big-name events), built on the relevance ranking. Foundation for
the GOAL's weekly emailer. Pure function, testable.
"""

from __future__ import annotations

from datetime import date
from xml.sax.saxutils import escape

from .config import SOURCES
from .models import Event
from .rank import event_kind, score_event, top_upcoming

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


_KIND_TAG = {"handson": "🔧 hands-on", "policy": "🏛️ policy",
             "networking": "🍸 networking", "talk": "🎙️ talk"}


def _line(ev: Event, today_iso: str) -> str:
    topics = ", ".join(_real_topics(ev)) or "—"
    src = _NAME.get(ev.source, ev.source)
    link = f" · [details]({ev.source_url})" if ev.source_url else ""
    star = "⭐ " if ev.is_big_name else ""
    kind = _KIND_TAG.get(event_kind(ev), "")
    return (f"**{(ev.start or '')[:10]}** — {star}{ev.title}  \n"
            f"  {src} · {kind} · {_loc(ev)} · {topics} · score {score_event(ev, today_iso)}{link}")


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


# ---------------------------------------------------------------------------
# Polished weekly email. Email clients routinely strip <head><style> and any
# external CSS, so every style here is INLINE on the element (also dodges
# f-string brace issues). Table-based layout for Outlook/Gmail compatibility.
# Distinct from render_html (that is the on-site web digest); this is the body
# the weekly emailer sends.
# ---------------------------------------------------------------------------
_E_BG = "#f4f6fb"      # page background
_E_CARD = "#ffffff"    # content card
_E_ACCENT = "#1a4fd0"  # links / section headers
_E_INK = "#1f2533"     # primary text
_E_MUTED = "#6b7280"   # secondary text
_E_PILL = "#eef3ff"    # date pill background


def _date_pill(iso: str) -> tuple[str, str]:
    """('Jun', '01') from an ISO start; ('', raw) if unparseable."""
    try:
        d = date.fromisoformat((iso or "")[:10])
        return d.strftime("%b"), d.strftime("%d")
    except ValueError:
        return "", (iso or "")[:10]


def _email_row(ev: Event, today_iso: str) -> str:
    mon, day = _date_pill(ev.start or "")
    title = _h(ev.title)
    if ev.source_url:
        title = (f'<a href="{_h(ev.source_url)}" style="color:{_E_INK};'
                 f'text-decoration:none">{title}</a>')
    star = '<span style="color:#d62728">★</span> ' if ev.is_big_name else ""
    topics = ", ".join(_real_topics(ev)) or "—"
    meta = f"{_h(_NAME.get(ev.source, ev.source))} &middot; {_h(_loc(ev))} &middot; {_h(topics)}"
    return (
        f'<tr><td style="padding:10px 0;border-bottom:1px solid #eef0f5">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        f'<td width="52" valign="top" align="center" '
        f'style="background:{_E_PILL};border-radius:8px;padding:6px 0">'
        f'<div style="font-size:11px;color:{_E_ACCENT};text-transform:uppercase;'
        f'font-weight:700">{mon}</div>'
        f'<div style="font-size:18px;color:{_E_INK};font-weight:700;line-height:1">{day}</div>'
        f'</td>'
        f'<td valign="top" style="padding-left:12px">'
        f'<div style="font-size:15px;font-weight:600;color:{_E_INK};line-height:1.35">'
        f'{star}{title}</div>'
        f'<div style="font-size:12px;color:{_E_MUTED};margin-top:3px">{meta}</div>'
        f'</td></tr></table></td></tr>'
    )


def _email_section(title: str, evs: list[Event], empty: str, today_iso: str) -> str:
    if evs:
        rows = "".join(_email_row(e, today_iso) for e in evs)
    else:
        rows = (f'<tr><td style="padding:10px 0;color:{_E_MUTED};font-size:13px">'
                f'{empty}</td></tr>')
    return (
        f'<tr><td style="padding:22px 0 4px;font-size:12px;font-weight:700;'
        f'letter-spacing:.05em;text-transform:uppercase;color:{_E_ACCENT}">{_h(title)}</td></tr>'
        f'<tr><td><table role="presentation" width="100%" cellpadding="0" '
        f'cellspacing="0">{rows}</table></td></tr>'
    )


def render_email_html(events: list[Event], today_iso: str,
                      new_events: list[Event] | None = None,
                      domain: str = "events.emersus.ai", top_n: int = 15,
                      unsubscribe_url: str = "#") -> str:
    """Polished, email-client-safe weekly digest. `new_events` (events first seen
    in the last week, from Store.new_since) are highlighted in their own section
    above the ranked upcoming list. Inline styles only. `unsubscribe_url` is
    filled per-recipient when sending (defaults to '#' for previews)."""
    new_events = new_events or []
    upcoming = [e for e in events if (e.start or "")[:10] >= today_iso]
    top = top_upcoming(events, today_iso, n=top_n)
    bigs = [e for e in top if e.is_big_name]
    new_up = sorted([e for e in new_events if (e.start or "")[:10] >= today_iso],
                    key=lambda e: e.start or "")

    gcal = ("https://calendar.google.com/calendar/r?cid=webcal%3A%2F%2F"
            + domain + "%2Fevents-upcoming.ics")
    sub = f"https://{domain}/events-upcoming.ics"

    inner = (
        _email_section(f"🆕 New this week ({len(new_up)})", new_up,
                       "Nothing new since last week — the calendar is current.", today_iso)
        + _email_section(f"⭐ Big names ({len(bigs)})", bigs,
                         "No marquee-org events in range right now.", today_iso)
        + _email_section(f"Top upcoming ({len(top)})", top,
                         "No upcoming events in range.", today_iso)
    )

    return (
        f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>DC AI &amp; Frontier Tech — Weekly</title></head>'
        f'<body style="margin:0;padding:0;background:{_E_BG};">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{_E_BG};padding:24px 12px"><tr><td align="center">'
        f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        f'style="max-width:600px;width:100%;background:{_E_CARD};border-radius:14px;'
        f'overflow:hidden;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">'
        # header band
        f'<tr><td style="background:{_E_ACCENT};padding:22px 26px">'
        f'<div style="font-size:19px;font-weight:700;color:#fff">DC AI &amp; Frontier Tech</div>'
        f'<div style="font-size:13px;color:#cfe0ff;margin-top:2px">'
        f'Weekly radar · AI / semiconductors / policy in the DC metro</div></td></tr>'
        # body
        f'<tr><td style="padding:8px 26px 26px">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        f'<tr><td style="font-size:13px;color:{_E_MUTED};padding:14px 0 0">'
        f'{today_iso} · {len(upcoming)} upcoming · {len(new_up)} new this week</td></tr>'
        f'<tr><td style="padding:14px 0 2px">'
        f'<a href="{gcal}" style="display:inline-block;background:{_E_ACCENT};color:#fff;'
        f'font-weight:600;font-size:14px;text-decoration:none;padding:10px 18px;'
        f'border-radius:8px">📅 Add to Google Calendar</a></td></tr>'
        f'{inner}'
        f'</table></td></tr>'
        # footer
        f'<tr><td style="background:#fafbfe;border-top:1px solid #eef0f5;padding:18px 26px;'
        f'font-size:12px;color:{_E_MUTED}">'
        f'You are subscribed to the DC AI &amp; Frontier Tech weekly radar.<br>'
        f'Subscribe in any calendar app: <a href="{sub}" style="color:{_E_ACCENT}">{sub}</a><br>'
        f'<a href="{_h(unsubscribe_url)}" style="color:{_E_MUTED}">Unsubscribe</a></td></tr>'
        f'</table></td></tr></table></body></html>'
    )
