"""Ground-truth accuracy check: for every kept UPCOMING event, fetch its own
source page and verify the stored title + date actually appear there. Covers the
new sources (itif/cdt/nasem/meetup) that lack JSON-LD, which the weekly --audit
can't verify. Reports per-event so a parsing drift / fabricated field is visible.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import date

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from aggregator.enrich import default_fetch  # noqa: E402
from aggregator.render import close_render, render  # noqa: E402
from aggregator.structured import extract_structured  # noqa: E402
from selectolax.parser import HTMLParser  # noqa: E402

TODAY = "2026-06-03"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())


def _tokens(s: str) -> set:
    return {w for w in _norm(s).split() if len(w) > 3}


def _date_forms(iso: str) -> list[str]:
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return [iso[:10]]
    return [iso[:10],
            f"{d.strftime('%B').lower()} {d.day}", f"{d.strftime('%b').lower()} {d.day}",
            f"{d.day} {d.strftime('%B').lower()}", f"{d.day} {d.strftime('%b').lower()}",  # day-first
            f"{d.month}/{d.day}/{d.year}", f"{d.strftime('%b').lower()} {d.day}, {d.year}"]


async def check(ev: dict) -> dict:
    url, src = ev.get("source_url", ""), ev.get("source", "")
    if not url:
        return {**ev, "verdict": "no-url"}
    try:
        html = await default_fetch(url, src)
    except Exception as e:  # noqa: BLE001
        return {**ev, "verdict": f"fetch-error {e!r}"[:50]}
    if not html:
        return {**ev, "verdict": "unreadable"}
    tree = HTMLParser(html)
    page = _norm(tree.text() if tree.body else html)
    st = extract_structured(html)
    # title: token overlap with the page (+ structured name when present)
    tt = _tokens(ev["title"])
    overlap = len(tt & _tokens(page)) / max(len(tt), 1)
    name_ok = bool(st.get("name")) and (len(_tokens(st["name"]) & tt) / max(len(tt), 1) >= 0.6)
    title_ok = overlap >= 0.6 or name_ok
    # date: stored date appears on the page in some human form, OR structured start matches
    forms = _date_forms(ev["start"])
    date_on_page = any(f in page for f in forms)
    # also accept a machine-readable ISO start in the raw HTML (e.g. a dc:date /
    # datetime content attr), which .text() strips out.
    iso_on_page = len(ev.get("start", "")) >= 16 and ev["start"][:16] in html
    struct_date_ok = (st.get("start", "")[:10] == ev["start"][:10]) if st.get("start") else None
    date_ok = date_on_page or iso_on_page or struct_date_ok is True
    # Fallback for JS-rendered pages (e.g. watchlist marquee sites): if the plain
    # fetch couldn't confirm the date but the title is on the page, render it
    # headless and re-check -- reuses the jsrender engine.
    via_render = False
    if not date_ok and title_ok:
        try:
            rhtml = await render(url)
        except Exception:  # noqa: BLE001
            rhtml = ""
        if rhtml:
            rfull = _norm(rhtml)   # norm the RAW html (catches dates in scripts/markup .text() drops)
            r_iso = len(ev.get("start", "")) >= 16 and ev["start"][:16] in rhtml
            if (any(f in rfull for f in forms) or r_iso
                    or extract_structured(rhtml).get("start", "")[:10] == ev["start"][:10]):
                date_ok = True
                via_render = True
    return {**ev, "title_overlap": round(overlap, 2), "title_ok": title_ok,
            "date_on_page": date_on_page, "struct_date": struct_date_ok,
            "date_ok": date_ok, "via_render": via_render,
            "verdict": "ok" if (title_ok and date_ok) else "REVIEW"}


async def main():
    evs = [e for e in json.load(open("out/events.json", encoding="utf-8"))
           if e.get("start", "")[:10] >= TODAY]
    print(f"Checking {len(evs)} upcoming kept events against their live source pages...\n")
    rows = await asyncio.gather(*[check(e) for e in evs])
    bad = 0
    for r in sorted(rows, key=lambda r: r["source"]):
        flag = "✅" if r["verdict"] == "ok" else "⚠️"
        if r["verdict"] != "ok":
            bad += 1
        print(f"{flag} [{r['source']:13}] {r['start'][:10]} {r['title'][:46]}")
        vr = " (via render)" if r.get("via_render") else ""
        print(f"     title_ok={r.get('title_ok')} (overlap={r.get('title_overlap')}) "
              f"date_ok={r.get('date_ok')}{vr} (on_page={r.get('date_on_page')} "
              f"struct={r.get('struct_date')}) {('| '+r['verdict']) if r['verdict'] not in ('ok','REVIEW') else ''}")
    await close_render()
    print(f"\n{len(rows)-bad}/{len(rows)} verified ok; {bad} need review.")


if __name__ == "__main__":
    asyncio.run(main())
