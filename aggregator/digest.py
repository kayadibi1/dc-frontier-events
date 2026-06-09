"""Weekly digest: a human-readable markdown summary of the top-ranked upcoming
events (and any big-name events), built on the relevance ranking. Foundation for
the GOAL's weekly emailer. Pure function, testable.
"""

from __future__ import annotations

from datetime import date
from xml.sax.saxutils import escape

from .config import SOURCES
from .models import Event
from .provenance import marker
from .rank import event_kind, score_event, top_upcoming

_NAME = {s.slug: s.name for s in SOURCES}


def _h(s: str) -> str:
    return escape(s or "", {'"': "&quot;"})


def _loc(ev: Event) -> str:
    base = ev.address if ev.address else ("virtual" if ev.raw.get("virtual") else "TBD")
    m = marker(ev)
    return f"{base} {m}" if (m and ev.address) else base


def _real_topics(ev: Event) -> list[str]:
    return [t for t in ev.topics if not t.startswith("big:")]


_KIND_TAG = {"handson": "🔧 hands-on", "policy": "🏛️ policy",
             "networking": "🍸 networking", "talk": "🎙️ talk"}


def _line(ev: Event, today_iso: str) -> str:
    topics = ", ".join(_real_topics(ev)) or "-"
    src = _NAME.get(ev.source, ev.source)
    link = f" · [details]({ev.source_url})" if ev.source_url else ""
    star = "⭐ " if ev.is_big_name else ""
    kind = _KIND_TAG.get(event_kind(ev), "")
    return (f"**{(ev.start or '')[:10]}** · {star}{ev.title}  \n"
            f"  {src} · {kind} · {_loc(ev)} · {topics} · score {score_event(ev, today_iso)}{link}")


def build_digest(events: list[Event], today_iso: str, top_n: int = 15) -> str:
    upcoming_all = [e for e in events if (e.start or "")[:10] >= today_iso]
    top = top_upcoming(events, today_iso, n=top_n)
    bigs = [e for e in top if e.is_big_name]

    out = [
        "# DC AI & Frontier Tech · Weekly Digest",
        f"_Generated {today_iso} · {len(upcoming_all)} upcoming event(s) across "
        f"{len({e.source for e in upcoming_all})} source(s)._",
        "",
        "## ⭐ Big names",
    ]
    if bigs:
        out += [f"- {_line(e, today_iso)}" for e in bigs]
    else:
        out.append("_None scheduled in range. DC big names cluster at Layer-2 "
                   "venues (CSET/CSIS); watch this section._")

    out += ["", f"## Top upcoming (ranked, showing {len(top)})"]
    if top:
        out += [f"{i}. {_line(e, today_iso)}" for i, e in enumerate(top, 1)]
    else:
        out.append("_No upcoming events in range._")
    out.append("")
    return "\n".join(out) + "\n"


_HTML_STYLE = (
    "body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:680px;"
    "margin:auto;background:#000;color:#f5f5f7;padding:16px}"
    "h1{font-size:20px;margin-bottom:2px;letter-spacing:-.02em}h2{font-size:15px;border-bottom:1px "
    "solid #424245;padding-bottom:4px;margin-top:24px}ul{list-style:none;padding:0}"
    "li{padding:8px 0;border-bottom:1px solid #2c2c2e}small{color:#a1a1a6}a{color:#2997ff}"
    ".meta{color:#86868b;font-size:13px}.star{color:#ff453a}"
)


def _html_item(ev: Event, today_iso: str) -> str:
    topics = ", ".join(_real_topics(ev)) or "-"
    star = '<span class="star">★</span> ' if ev.is_big_name else ""
    link = f' · <a href="{_h(ev.source_url)}">details</a>' if ev.source_url else ""
    return (f"<li><b>{(ev.start or '')[:10]}</b> · {star}{_h(ev.title)}<br>"
            f"<small>{_h(_NAME.get(ev.source, ev.source))} · {_h(_loc(ev))} · "
            f"{_h(topics)} · score {score_event(ev, today_iso)}{link}</small></li>")


def render_html(events: list[Event], today_iso: str, top_n: int = 15) -> str:
    """HTML rendering of the digest (web + email body). Self-contained, inline <style>."""
    upcoming = [e for e in events if (e.start or "")[:10] >= today_iso]
    top = top_upcoming(events, today_iso, n=top_n)
    bigs = [e for e in top if e.is_big_name]
    big_html = "".join(_html_item(e, today_iso) for e in bigs) or \
        "<li><small>None scheduled in range. DC big names cluster at CSET/CSIS.</small></li>"
    top_html = "".join(_html_item(e, today_iso) for e in top) or \
        "<li><small>No upcoming events in range.</small></li>"
    return (
        f"<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<link rel=\"icon\" type=\"image/svg+xml\" href=\"/favicon.svg\">"
        f"<title>DC AI &amp; Frontier Tech · Weekly Digest</title><style>{_HTML_STYLE}</style></head>"
        f"<body><h1>DC AI &amp; Frontier Tech · Weekly Digest</h1>"
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
_E_BG = "#000000"      # page background (Pro dark)
_E_CARD = "#1d1d1f"    # content card
_E_ACCENT = "#2997ff"  # links / section headers (Apple dark-mode blue)
_E_INK = "#f5f5f7"     # primary text
_E_MUTED = "#a1a1a6"   # secondary text (AA on dark surfaces)
_E_PILL = "#2c2c2e"    # date pill background
_E_LINE = "#424245"    # hairlines
_E_META = ('<meta name="color-scheme" content="dark">'
           '<meta name="supported-color-schemes" content="dark">')


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
    star = '<span style="color:#ff453a">★</span> ' if ev.is_big_name else ""
    topics = ", ".join(_real_topics(ev)) or "-"
    meta = f"{_h(_NAME.get(ev.source, ev.source))} &middot; {_h(_loc(ev))} &middot; {_h(topics)}"
    return (
        f'<tr><td style="padding:10px 0;border-bottom:1px solid {_E_LINE}">'
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
                       "Nothing new since last week. The calendar is current.", today_iso)
        + _email_section(f"⭐ Big names ({len(bigs)})", bigs,
                         "No marquee-org events in range right now.", today_iso)
        + _email_section(f"Top upcoming ({len(top)})", top,
                         "No upcoming events in range.", today_iso)
    )

    return (
        f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'{_E_META}'
        f'<title>DC AI &amp; Frontier Tech · Weekly</title></head>'
        f'<body style="margin:0;padding:0;background:{_E_BG};">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'bgcolor="#000000" style="background:{_E_BG};padding:24px 12px"><tr><td align="center">'
        f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        f'style="max-width:600px;width:100%;background:{_E_CARD};border:1px solid {_E_LINE};'
        f'border-radius:16px;'
        f'overflow:hidden;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">'
        # header band
        f'<tr><td style="background:#000000;padding:22px 26px">'
        f'<div style="font-size:19px;font-weight:700;color:{_E_INK};'
        f'letter-spacing:-.02em">DC AI &amp; Frontier Tech</div>'
        f'<div style="font-size:13px;color:{_E_MUTED};margin-top:2px">'
        f'Weekly radar · AI / semiconductors / policy in the DC metro</div></td></tr>'
        # body
        f'<tr><td style="padding:8px 26px 26px">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        f'<tr><td style="font-size:13px;color:{_E_MUTED};padding:14px 0 0">'
        f'{today_iso} · {len(upcoming)} upcoming · {len(new_up)} new this week</td></tr>'
        f'<tr><td style="padding:14px 0 2px">'
        # Button fill via td bgcolor: Outlook's Word renderer drops CSS
        # background on <a> but honors the attribute (black-on-black otherwise).
        f'<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
        f'<td bgcolor="{_E_ACCENT}" style="background:{_E_ACCENT};border-radius:980px">'
        f'<a href="{gcal}" style="display:inline-block;color:#000000;'
        f'font-weight:600;font-size:14px;text-decoration:none;padding:10px 18px">'
        f'📅 Add to Google Calendar</a></td></tr></table></td></tr>'
        f'{inner}'
        f'</table></td></tr>'
        # footer
        f'<tr><td style="background:#000000;border-top:1px solid {_E_LINE};padding:18px 26px;'
        f'font-size:12px;color:{_E_MUTED}">'
        f'You are subscribed to the DC AI &amp; Frontier Tech weekly radar.<br>'
        f'Subscribe in any calendar app: <a href="{sub}" style="color:{_E_ACCENT}">{sub}</a><br>'
        f'<a href="{_h(unsubscribe_url)}" style="color:{_E_MUTED}">Unsubscribe</a></td></tr>'
        f'</table></td></tr></table></body></html>'
    )


# ---------------------------------------------------------------------------
# Transactional emails for the double-opt-in signup flow: the verify email (sent
# on signup) and the welcome email (sent after the verify click, with a Top-3
# "taste" of upcoming events). Same email-client-safe card chrome as the weekly
# digest; inline styles only.
# ---------------------------------------------------------------------------
def _email_shell(heading: str, body_html: str, footer_html: str,
                 title: str = "DC AI & Frontier Tech") -> str:
    """Wrap body_html in the shared card chrome (dark header band + footer)."""
    return (
        f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'{_E_META}'
        f'<title>{_h(title)}</title></head>'
        f'<body style="margin:0;padding:0;background:{_E_BG};">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'bgcolor="#000000" style="background:{_E_BG};padding:24px 12px"><tr><td align="center">'
        f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        f'style="max-width:600px;width:100%;background:{_E_CARD};border:1px solid {_E_LINE};'
        f'border-radius:16px;'
        f'overflow:hidden;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">'
        f'<tr><td style="background:#000000;padding:22px 26px">'
        f'<div style="font-size:19px;font-weight:700;color:{_E_INK};'
        f'letter-spacing:-.02em">{_h(heading)}</div>'
        f'<div style="font-size:13px;color:{_E_MUTED};margin-top:2px">'
        f'Weekly radar · AI / semiconductors / policy in the DC metro</div></td></tr>'
        f'<tr><td style="padding:20px 26px 24px">{body_html}</td></tr>'
        f'<tr><td style="background:#000000;border-top:1px solid {_E_LINE};padding:16px 26px;'
        f'font-size:12px;color:{_E_MUTED}">{footer_html}</td></tr>'
        f'</table></td></tr></table></body></html>'
    )


def _gcal_button(domain: str) -> str:
    gcal = ("https://calendar.google.com/calendar/r?cid=webcal%3A%2F%2F"
            + domain + "%2Fevents-upcoming.ics")
    return (f'<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
            f'<td bgcolor="{_E_ACCENT}" style="background:{_E_ACCENT};border-radius:980px">'
            f'<a href="{gcal}" style="display:inline-block;color:#000000;'
            f'font-weight:600;font-size:14px;text-decoration:none;padding:11px 20px">'
            f'📅 Add to Google Calendar</a></td></tr></table>')


def render_verify_email_html(verify_url: str,
                             domain: str = "events.emersus.ai") -> str:
    """Confirmation email: one clear button to verify the subscription. No event
    content -- it exists only to prove the address is real (double opt-in)."""
    body = (
        f'<p style="font-size:15px;color:{_E_INK};line-height:1.5;margin:6px 0 4px">'
        f'Almost there. Please confirm your email to start getting the weekly '
        f'DC AI &amp; frontier-tech radar.</p>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:20px 0"><tr>'
        f'<td bgcolor="{_E_ACCENT}" style="background:{_E_ACCENT};border-radius:980px">'
        f'<a href="{_h(verify_url)}" style="display:inline-block;'
        f'color:#000000;font-weight:600;font-size:15px;text-decoration:none;padding:12px 22px">'
        f'Confirm my subscription</a></td></tr></table>'
        f'<p style="font-size:13px;color:{_E_MUTED};line-height:1.5;margin:4px 0">'
        f'This link expires in 48 hours. If the button does not work, copy this URL '
        f'into your browser:<br><span style="color:{_E_ACCENT};word-break:break-all">'
        f'{_h(verify_url)}</span></p>'
    )
    footer = ("If you did not sign up, just ignore this email. No subscription is "
              "created until you click the button above.")
    return _email_shell("Confirm your subscription", body, footer)


def render_welcome_email_html(events: list[Event], today_iso: str,
                              unsubscribe_url: str = "#",
                              domain: str = "events.emersus.ai",
                              taste_n: int = 3) -> str:
    """Welcome email sent right after verification. Hero is the Add-to-Google-
    Calendar button (that gives the FULL live list); below it a Top-`taste_n`
    sampler of upcoming events as a teaser, explicitly pointing to Monday's full
    digest so the weekly send is never redundant."""
    taste = top_upcoming(events, today_iso, n=taste_n)
    sub = f"https://{domain}/events-upcoming.ics"
    if taste:
        rows = "".join(_email_row(e, today_iso) for e in taste)
        taste_block = (
            f'<div style="font-size:12px;font-weight:700;letter-spacing:.05em;'
            f'text-transform:uppercase;color:{_E_ACCENT};padding:6px 0 2px">'
            f'A taste of what&rsquo;s on the radar</div>'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'{rows}</table>'
            f'<p style="font-size:13px;color:{_E_MUTED};margin:14px 0 0">'
            f'Your full weekly digest, with everything new, lands Monday morning.</p>'
        )
    else:
        taste_block = (
            f'<p style="font-size:13px;color:{_E_MUTED};margin:14px 0 0">'
            f'Nothing on the calendar right now, but your first weekly digest lands '
            f'Monday morning.</p>')
    body = (
        f'<p style="font-size:17px;font-weight:700;color:{_E_INK};margin:4px 0 2px">'
        f'You&rsquo;re in. ✅</p>'
        f'<p style="font-size:14px;color:{_E_MUTED};line-height:1.5;margin:0 0 16px">'
        f'Add the calendar below for the full live list of events. It always stays '
        f'current. The email is just the highlights.</p>'
        f'<p style="margin:0 0 18px">{_gcal_button(domain)}</p>'
        f'{taste_block}'
    )
    footer = (
        f'You are subscribed to the DC AI &amp; Frontier Tech weekly radar.<br>'
        f'Subscribe in any calendar app: <a href="{sub}" style="color:{_E_ACCENT}">{sub}</a><br>'
        f'<a href="{_h(unsubscribe_url)}" style="color:{_E_MUTED}">Unsubscribe</a>')
    return _email_shell("Welcome aboard", body, footer)
