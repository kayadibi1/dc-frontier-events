# Live Event Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** A read-only weekly `--audit` that re-fetches think-tank events' live source pages and diffs date/title/location against the store, writing `out/audit.md` with honest verdicts.

**Architecture:** `extract_structured` gains `name`. New `audit.py` has `audit_events` (async, injected fetch → offline-testable), `render_audit_md` (pure), and `run_audit` (glue: store → upcoming think-tank events → cap → fetch → report). `--audit` short-circuits in `__main__`. A weekly systemd template is added. Nothing in the pipeline/feeds changes.

**Spec:** `docs/superpowers/specs/2026-06-02-live-audit-design.md`. Branch: `sp4-audit`.

---

### Task 1: `structured.py` — return `name`

**Files:** Modify `aggregator/structured.py`; append `tests/test_structured.py`

- [ ] **Step 1: Failing test** (append):
```python
def test_extract_structured_returns_name():
    html = ('<script type="application/ld+json">{"@type":"Event","name":"AI Policy Panel",'
            '"startDate":"2026-07-01"}</script>')
    assert extract_structured(html)["name"] == "AI Policy Panel"
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_structured.py -k name -q` → FAIL (KeyError)

- [ ] **Step 3: Edit `structured.py`** — in `extract_structured`, after the start/end loop add:
```python
    name = node.get("name")
    if isinstance(name, str) and name.strip():
        out["name"] = name.strip()
```

- [ ] **Step 4: Run, verify pass** — `python -m pytest tests/test_structured.py -q` → PASS

- [ ] **Step 5: Commit**
```bash
git add aggregator/structured.py tests/test_structured.py
git commit -m "feat(structured): return schema.org Event name"
```

---

### Task 2: `audit.py` — `audit_events` diff logic

**Files:** Create `aggregator/audit.py`, `tests/test_audit.py`

- [ ] **Step 1: Failing tests** — `tests/test_audit.py`:
```python
import asyncio

from aggregator.audit import audit_events
from aggregator.models import Event
from aggregator.provenance import prov_set

T = "2026-06-02"
JSONLD = ('<script type="application/ld+json">{{"@type":"Event","name":"{name}",'
          '"startDate":"{start}"}}</script>')


def _run(ev, html):
    return asyncio.run(audit_events([ev], lambda url, kind: _aret(html), T))[0]


async def _aret(html):
    return html


def test_match():
    ev = Event(id="1", title="AI Policy Panel", start="2026-06-10T10:00:00-04:00", source="csis",
               source_url="http://x")
    row = _run(ev, JSONLD.format(name="AI Policy Panel", start="2026-06-10T10:00:00-04:00"))
    assert row["status"] == "read" and row["date"] == "match" and row["title_verdict"] == "match"


def test_date_mismatch():
    ev = Event(id="2", title="P", start="2026-06-10", source="csis", source_url="http://x")
    row = _run(ev, JSONLD.format(name="P", start="2026-06-17"))
    assert "mismatch" in row["date"]


def test_date_no_false_mismatch_csis_naive_utc():
    # stored 10pm EDT == 2am next-day UTC; live naive-UTC must normalize -> same date
    ev = Event(id="3", title="P", start="2026-06-04T22:00:00-04:00", source="csis", source_url="http://x")
    row = _run(ev, JSONLD.format(name="P", start="2026-06-05T02:00:00"))
    assert row["date"] == "match"


def test_title_punct_match_and_suffix_strip():
    ev = Event(id="4", title="AI & Chips: 2026", start="2026-06-10", source="csis", source_url="http://x")
    # og:title with site suffix, no JSON-LD name
    html = '<meta property="og:title" content="AI &amp; Chips 2026 | CSIS">'
    row = _run(ev, html)
    assert row["title_verdict"] == "match"


def test_title_mismatch():
    ev = Event(id="5", title="Old Title", start="2026-06-10", source="csis", source_url="http://x")
    row = _run(ev, JSONLD.format(name="Completely Different", start="2026-06-10"))
    assert row["title_verdict"] == "mismatch"


def test_unreadable_empty_and_raises():
    ev = Event(id="6", title="P", start="2026-06-10", source="csis", source_url="http://x")
    empty = _run(ev, "")
    assert empty["status"] == "unreadable"

    async def boom(url, kind):
        raise OSError("down")
    row = asyncio.run(audit_events([ev], boom, T))[0]
    assert row["status"] == "unreadable"


def test_unverifiable_when_no_ground_truth():
    ev = Event(id="7", title="P", start="2026-06-10", source="csis", source_url="http://x")
    row = _run(ev, "<p>just text, no event markup</p>")
    assert row["date"] == "unverifiable" and row["title_verdict"] == "unverifiable"


def test_location_note_for_hq_with_live_venue():
    ev = Event(id="8", title="P", start="2026-06-10", source="csis", source_url="http://x",
               address="CSIS HQ")
    prov_set(ev, "location", "hq")
    html = ('<script type="application/ld+json">{"@type":"Event","name":"P","startDate":"2026-06-10",'
            '"location":{"@type":"Place","name":"Real Hall","address":{"@type":"PostalAddress",'
            '"streetAddress":"9 X St","addressLocality":"Washington","addressRegion":"DC","postalCode":"20001"}}}</script>')
    row = _run(ev, html)
    assert "live venue available" in row["location_note"]


def test_date_only_live_no_false_mismatch():
    ev = Event(id="9", title="P", start="2026-06-10T10:00:00-04:00", source="csis", source_url="http://x")
    row = _run(ev, JSONLD.format(name="P", start="2026-06-10"))   # live is date-only
    assert row["date"] == "match"


def test_location_note_venue_only():
    ev = Event(id="10", title="P", start="2026-06-10", source="csis", source_url="http://x", address="CSIS HQ")
    prov_set(ev, "location", "hq")
    html = ('<script type="application/ld+json">{"@type":"Event","name":"P","startDate":"2026-06-10",'
            '"location":{"@type":"Place","name":"Real Hall"}}</script>')
    row = _run(ev, html)
    assert "Real Hall" in row["location_note"]
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_audit.py -q` → FAIL (no module)

- [ ] **Step 3: Implement `aggregator/audit.py`** (audit_events + helpers)
```python
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
        # date
        date_verdict = _audit_date(ev, st.get("start"))
        # title
        live_title = st.get("name") or _og_title(html)
        if not live_title:
            title_verdict = "unverifiable"
        elif _norm_title(live_title) == _norm_title(ev.title):
            title_verdict = "match"
        else:
            title_verdict = "mismatch"
        # location note
        note = ""
        if prov_get(ev, "location") == "hq" and (st.get("venue_name") or st.get("address")):
            note = f"live venue available: {st.get('venue_name') or st.get('address')}"
        rows.append({"id": ev.id, "source": ev.source, "title": ev.title,
                     "status": "read", "date": date_verdict,
                     "title_verdict": title_verdict, "location_note": note})
    return rows
```

- [ ] **Step 4: Run, verify pass** — `python -m pytest tests/test_audit.py -q` → PASS (8)

- [ ] **Step 5: Commit**
```bash
git add aggregator/audit.py tests/test_audit.py
git commit -m "feat(audit): audit_events live-vs-stored diff (date/title/location)"
```

---

### Task 3: `render_audit_md` + `run_audit` + `--audit` CLI + deploy timer

**Files:** Modify `aggregator/audit.py`, `aggregator/__main__.py`; create `deploy/dc-frontier-events-audit.service`, `deploy/dc-frontier-events-audit.timer`; append `tests/test_audit.py`

- [ ] **Step 1: Failing test** (append to `tests/test_audit.py`):
```python
def test_render_audit_md_escapes_and_summarizes():
    from aggregator.audit import render_audit_md
    rows = [
        {"id": "1", "source": "csis", "title": "A | B", "status": "read",
         "date": "match", "title_verdict": "mismatch", "location_note": ""},
        {"id": "2", "source": "cnas", "title": "C", "status": "unreadable",
         "date": "", "title_verdict": "", "location_note": ""},
        {"id": "3", "source": "csis", "title": "D", "status": "read",
         "date": "unverifiable", "title_verdict": "unverifiable", "location_note": ""},
    ]
    md = render_audit_md(rows, "2026-06-02")
    assert "A \\| B" in md                  # pipe escaped so the table doesn't break
    assert "1 mismatch" in md and "1 unverifiable" in md and "1 unreadable" in md
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_audit.py -k render -q` → FAIL

- [ ] **Step 3a: Add `render_audit_md` + `run_audit` to `audit.py`**
```python
import os

from .emit import filter_upcoming
from .enrich import default_fetch
from .storage import open_store

AUDIT_SOURCES = {"cset", "csis", "brookings", "cnas", "atlanticcouncil"}
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
            date_c, title_c = "🚫 unreadable", "🚫 unreadable"
        else:
            date_c = f"{_VERDICT_ICON.get(r['date'].split(' ')[0], '')} {r['date']}".strip()
            title_c = f"{_VERDICT_ICON.get(r['title_verdict'], '')} {r['title_verdict']}".strip()
        out.append(f"| {_cell(r['source'])} | {_cell(r['title'][:50])} | {_cell(date_c)} | "
                   f"{_cell(title_c)} | {_cell(r['location_note'])} |")
    return "\n".join(out) + "\n"


def run_audit(today_iso: str | None = None, out_dir: str = "out",
              db_path: str = "data/events.db") -> dict:
    import sys
    from datetime import date
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    today = today_iso or date.today().isoformat()
    store = open_store(db_path)
    active = store.active_events()
    store.close()
    eligible = [e for e in filter_upcoming(active, today)
                if e.source in AUDIT_SOURCES and e.source_url]
    print(f"\nLive audit — {today}: {len(eligible)} eligible upcoming think-tank event(s)")
    audited = eligible[:AUDIT_MAX]
    if len(eligible) > AUDIT_MAX:
        print(f"  (capped at AUDIT_MAX={AUDIT_MAX}; {len(eligible) - AUDIT_MAX} not audited)")
    import asyncio
    rows = asyncio.run(audit_events(audited, default_fetch, today))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "audit.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_audit_md(rows, today))
    n_mis = sum(1 for r in rows if "mismatch" in r["date"] or r["title_verdict"] == "mismatch")
    n_unread = sum(1 for r in rows if r["status"] == "unreadable")
    print(f"  audited {len(rows)}; {n_mis} mismatch, {n_unread} unreadable -> {path}\n")
    return {"audited": len(rows), "mismatch": n_mis, "unreadable": n_unread}
```

- [ ] **Step 3b: Edit `__main__.py`** — add the flag and short-circuit. After the `--email` argument add:
```python
    p.add_argument("--audit", action="store_true",
                   help="live ground-truth audit: re-fetch think-tank event pages and "
                        "diff date/title/location vs the store (writes out/audit.md); skips the pipeline")
```
and after the `if args.email:` block add:
```python
    if args.audit:
        from .audit import run_audit
        run_audit(today_iso=args.today, out_dir=args.out, db_path=args.db)
        return
```

- [ ] **Step 3c: Create `deploy/dc-frontier-events-audit.service`**
```ini
# Weekly live ground-truth audit (sub-project 4). Install on the box manually:
#   cp deploy/dc-frontier-events-audit.* /etc/systemd/system/ && systemctl enable --now dc-frontier-events-audit.timer
[Unit]
Description=DC Frontier Events — weekly live audit
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=emersus
WorkingDirectory=/opt/dc-frontier-events
EnvironmentFile=/etc/dc-frontier-events.env
ExecStart=/opt/dc-frontier-events/.venv/bin/python -m aggregator --audit --out /opt/dc-frontier-events/out
TimeoutStartSec=600
```
**Create `deploy/dc-frontier-events-audit.timer`**
```ini
[Unit]
Description=Run the DC Frontier Events live audit weekly

[Timer]
OnCalendar=Mon 06:00
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 4: Run, verify pass + full suite** — `python -m pytest tests/test_audit.py -q` → PASS; `python -m pytest -q` → all green; `python -m aggregator --help` shows `--audit`.

- [ ] **Step 5: Commit**
```bash
git add aggregator/audit.py aggregator/__main__.py deploy/dc-frontier-events-audit.service deploy/dc-frontier-events-audit.timer tests/test_audit.py
git commit -m "feat(audit): render_audit_md + run_audit + --audit CLI + weekly timer"
```

---

### Task 4: Verify + merge

- [ ] **Step 1: Full suite** — `python -m pytest -q` → all green.
- [ ] **Step 2: Offline CLI smoke (empty DB → no network)** — `python -m aggregator --audit --out out_e2e --db data/audit-smoke-empty.db` (empty store → 0 eligible, writes an empty-table audit.md, no fetch). Confirm `out_e2e/audit.md` exists and the pipeline/feeds are untouched.
- [ ] **Step 3: Clean** — `rm -rf out_e2e data/audit-smoke-empty.db`
- [ ] **Step 4: Merge** — `git switch master && git merge --ff-only sp4-audit && git push origin master`

---

## Self-Review

**Spec coverage:** `name` in structured (T1) ✓; audit_events with tz-aware date, normalized+suffix title, fetch try/except, hq location note (T2) ✓; render escapes `|` + summary, run_audit with AUDIT_SOURCES/AUDIT_MAX/upcoming, `--audit` CLI, deploy timer (T3) ✓; verify+merge (T4) ✓.

**Placeholder scan:** none — concrete code/commands throughout.

**Type consistency:** `audit_events(events, fetch, today_iso)->list[dict]` rows `{id,source,title,status,date,title_verdict,location_note}` used consistently in T2/T3; `render_audit_md(rows, today)->str`; `run_audit(today_iso,out_dir,db_path)->dict`; reuses real `extract_structured` (now with `name`), `filter_upcoming`, `default_fetch`, `open_store().active_events()`, `prov_get`.
