"""Live ground-truth audit (sub-project 4): re-fetch a stored event's own source page
and diff date/title/location against what we stored. Read-only -- it REPORTS, never
mutates feeds. `audit_events` takes an injected async `fetch`, so it is fully
offline-testable; `run_audit` (below) wires it to the store + default_fetch.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from html import unescape

from selectolax.parser import HTMLParser

from .emit import filter_upcoming
from .enrich import default_fetch
from .models import Event
from .provenance import prov_get
from .storage import open_store
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


AUDIT_SOURCES = {"cset", "csis", "brookings", "cnas", "atlanticcouncil", "nist"}
AUDIT_MAX = int(os.environ.get("AUDIT_MAX", "60"))

_VERDICT_ICON = {"match": "✅", "mismatch": "⚠️", "unverifiable": "❔", "unreadable": "🚫", "": ""}


def _cell(s: str) -> str:
    return (s or "").replace("|", "\\|")


def render_audit_md(rows: list[dict], today_iso: str) -> str:
    n_mis = sum(1 for r in rows if "mismatch" in r["date"] or r["title_verdict"] == "mismatch")
    n_unread = sum(1 for r in rows if r["status"] == "unreadable")
    n_unver = sum(1 for r in rows if r["status"] == "read"
                  and "mismatch" not in r["date"] and r["title_verdict"] != "mismatch"
                  and "unverifiable" in (r["date"], r["title_verdict"]))
    out = ["# Live Event Audit",
           f"_Generated {today_iso}. {len(rows)} event(s) audited; "
           f"{n_mis} mismatch, {n_unver} unverifiable, {n_unread} unreadable._", "",
           "| Source | Event | Date | Title | Note |", "|---|---|---|---|---|"]
    for r in rows:
        if r["status"] == "unreadable":
            date_c = title_c = "🚫 unreadable"
        else:
            date_c = f"{_VERDICT_ICON.get(r['date'].split(' ')[0], '')} {r['date']}".strip()
            title_c = f"{_VERDICT_ICON.get(r['title_verdict'], '')} {r['title_verdict']}".strip()
        out.append(f"| {_cell(r['source'])} | {_cell(r['title'][:50])} | {_cell(date_c)} | "
                   f"{_cell(title_c)} | {_cell(r['location_note'])} |")
    return "\n".join(out) + "\n"


def run_audit(today_iso: str | None = None, out_dir: str = "out",
              db_path: str = "data/events.db") -> dict:
    import asyncio
    import sys
    from datetime import date
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    today = today_iso or date.today().isoformat()
    store = open_store(db_path)
    try:
        active = store.active_events()
    finally:
        store.close()
    eligible = [e for e in filter_upcoming(active, today)
                if e.source in AUDIT_SOURCES and e.source_url]
    print(f"\nLive audit — {today}: {len(eligible)} eligible upcoming think-tank event(s)")
    audited = eligible[:AUDIT_MAX]
    if len(eligible) > AUDIT_MAX:
        print(f"  (capped at AUDIT_MAX={AUDIT_MAX}; {len(eligible) - AUDIT_MAX} not audited)")
    rows = asyncio.run(audit_events(audited, default_fetch, today))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "audit.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_audit_md(rows, today))
    n_mis = sum(1 for r in rows if "mismatch" in r["date"] or r["title_verdict"] == "mismatch")
    n_unread = sum(1 for r in rows if r["status"] == "unreadable")
    print(f"  audited {len(rows)}; {n_mis} mismatch, {n_unread} unreadable -> {path}\n")
    return {"audited": len(rows), "mismatch": n_mis, "unreadable": n_unread}
