"""Live ground-truth audit (sub-project 4): re-fetch a stored event's own source page
and diff date/title/location against what we stored. Read-only -- it REPORTS, never
mutates feeds. `audit_events` takes an injected async `fetch`, so it is fully
offline-testable; `run_audit` (below) wires it to the store + default_fetch.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from html import unescape

from selectolax.parser import HTMLParser

from .models import Event
from .provenance import prov_get
from .structured import extract_structured

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")
# Common site suffixes appended to og:title.
_SUFFIX = re.compile(r"\s*[|\-–—]\s*(CSIS|Brookings|CNAS|Atlantic Council|CSET)\s*$", re.I)


def _og_title(html: str) -> str:
    node = HTMLParser(html or "").css_first('meta[property="og:title"]')
    if not node:
        return ""
    return _SUFFIX.sub("", unescape((node.attributes.get("content") or "")).strip())


def _norm_title(s: str) -> str:
    return _WS.sub(" ", _PUNCT.sub(" ", (s or "").casefold())).strip()


def _audit_date(ev: Event, live: str | None) -> str:
    stored = ev.start or ""
    if not live:
        return "unverifiable"
    if "T" not in live:                      # live date-only -> compare dates directly
        a, b = stored[:10], live[:10]
        return "match" if a == b else f"mismatch ({a} -> {b})"
    try:
        sdt = datetime.fromisoformat(stored)
        ldt = datetime.fromisoformat(live)
    except ValueError:
        a, b = stored[:10], live[:10]
        return "match" if a == b else f"mismatch ({a} -> {b})"
    # CSIS emits naive UTC; ONLY then attach UTC and convert to the stored offset.
    if ev.source == "csis" and ldt.tzinfo is None and sdt.tzinfo is not None:
        ldt = ldt.replace(tzinfo=timezone.utc).astimezone(sdt.tzinfo)
    a, b = sdt.date().isoformat(), ldt.date().isoformat()
    return "match" if a == b else f"mismatch ({a} -> {b})"


async def audit_events(events: list[Event], fetch, today_iso: str) -> list[dict]:
    rows = []
    for ev in events:
        try:
            html = await fetch(ev.source_url, ev.source)
        except Exception:
            html = ""
        if not html:
            rows.append({"id": ev.id, "source": ev.source, "title": ev.title,
                         "status": "unreadable", "date": "", "title_verdict": "",
                         "location_note": ""})
            continue
        st = extract_structured(html)
        date_verdict = _audit_date(ev, st.get("start"))
        live_title = st.get("name") or _og_title(html)
        if not live_title:
            title_verdict = "unverifiable"
        elif _norm_title(live_title) == _norm_title(ev.title):
            title_verdict = "match"
        else:
            title_verdict = "mismatch"
        note = ""
        if prov_get(ev, "location") == "hq" and (st.get("venue_name") or st.get("address")):
            note = f"live venue available: {st.get('venue_name') or st.get('address')}"
        rows.append({"id": ev.id, "source": ev.source, "title": ev.title,
                     "status": "read", "date": date_verdict,
                     "title_verdict": title_verdict, "location_note": note})
    return rows
