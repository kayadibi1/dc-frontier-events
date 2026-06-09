# Luma ICS → JSON Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Luma ICS layer with Luma's JSON APIs and add a city-wide DC discover source, per `docs/superpowers/specs/2026-06-09-luma-json-migration-design.md`.

**Architecture:** Rewrite `aggregator/fetchers/luma.py` around two endpoints — `api.lu.ma/calendar/get-items` (per calendar, `period=future`) and `api.lu.ma/discover/get-paginated-events` (DC place feed) — sharing one pure JSON→Event mapper and one pagination loop with an injectable async `get_json` (the codebase's enrich/audit DI test pattern). Event ids are the same `evt-XXX` the ICS UIDs normalized to, so the store and dedupe carry over unchanged.

**Tech Stack:** Python 3.12+, httpx (async), zoneinfo, pytest. No new dependencies.

**Verified live facts the code relies on (probed 2026-06-09):**
- `get-items?calendar_api_id=cal-…&period=future&pagination_limit=N` → `{"entries":[{"event":{…}}],"has_more":bool,"next_cursor":str}`; page 2 via `&pagination_cursor=<cursor>` (cursor is URL-unsafe base64 — quote it).
- `get-paginated-events?discover_place_api_id=discplace-AANPgOymN6bqFn8&pagination_limit=N` → same entry shape.
- Event JSON fields: `api_id` ("evt-…"), `name`, `start_at`/`end_at` (UTC ISO, `.000Z`), `timezone` (IANA), `location_type` ("offline"/"online"), `geo_address_info{full_address,address,city_state}`, `coordinate{latitude,longitude}`, `url` (slug → `https://lu.ma/<slug>`). No description field (ICS desc was boilerplate; topics stay title-based).

---

### Task 1: Capture real JSON fixtures

**Files:**
- Create: `tests/fixtures/luma_get_items.json`
- Create: `tests/fixtures/luma_discover.json`

- [ ] **Step 1: Capture both endpoint responses**

```bash
curl -s "https://api.lu.ma/calendar/get-items?calendar_api_id=cal-eCuIBRbS1atJOa6&period=future&pagination_limit=50" -o tests/fixtures/luma_get_items.json
curl -s "https://api.lu.ma/discover/get-paginated-events?discover_place_api_id=discplace-AANPgOymN6bqFn8&pagination_limit=50" -o tests/fixtures/luma_discover.json
```

- [ ] **Step 2: Verify both contain entries**

Run: `python -c "import json; a=json.load(open('tests/fixtures/luma_get_items.json')); b=json.load(open('tests/fixtures/luma_discover.json')); print(len(a['entries']), len(b['entries']))"`
Expected: two numbers, both >= 1

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/luma_get_items.json tests/fixtures/luma_discover.json
git commit -m "test(luma): capture real get-items + discover JSON fixtures"
```

---

### Task 2: Pure mapper `event_from_json` (TDD)

**Files:**
- Create: `tests/test_luma.py`
- Modify: `aggregator/fetchers/luma.py` (add mapper; keep the ICS `fetch_luma` working for now)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_luma.py`:

```python
import json
import os

from aggregator.config import Source
from aggregator.fetchers.luma import event_from_json
from aggregator.provenance import prov_get

SRC = Source("DC2", "DC Data & AI Events", "luma", 1, True, cal_id="cal-x")

ENTRY = {
    "event": {
        "api_id": "evt-uAm3FAMHeYgxVNx",
        "name": "Side Projects: AI Meetup",
        "start_at": "2026-06-10T22:00:00.000Z",
        "end_at": "2026-06-11T00:00:00.000Z",
        "timezone": "America/New_York",
        "location_type": "offline",
        "url": "thq3hut1",
        "geo_address_info": {
            "address": "2112 Pennsylvania Ave NW",
            "city_state": "Washington, District of Columbia",
            "full_address": "2112 Pennsylvania Ave NW, Washington, DC 20037, USA",
        },
        "coordinate": {"longitude": -77.0479011, "latitude": 38.9014337},
    }
}


def test_maps_core_fields():
    ev = event_from_json(SRC, ENTRY)
    assert ev.id == "evt-uAm3FAMHeYgxVNx"          # same id the ICS UID normalized to
    assert ev.title == "Side Projects: AI Meetup"
    assert ev.source == "DC2"
    assert ev.source_url == "https://lu.ma/thq3hut1"
    assert ev.organizer == "DC Data & AI Events"
    assert "ai" in ev.topics


def test_start_is_venue_local_tz_aware():
    ev = event_from_json(SRC, ENTRY)
    assert ev.start == "2026-06-10T18:00:00-04:00"   # 22:00 UTC -> 18:00 ET
    assert ev.end == "2026-06-10T20:00:00-04:00"
    assert ev.tz == "America/New_York"


def test_structured_location_and_coords():
    ev = event_from_json(SRC, ENTRY)
    assert ev.address == "2112 Pennsylvania Ave NW, Washington, DC 20037, USA"
    assert ev.venue_name == "2112 Pennsylvania Ave NW"
    assert ev.lat == 38.9014337 and ev.lng == -77.0479011
    assert prov_get(ev, "location") == "structured"
    assert not ev.raw.get("virtual")


def test_online_event_is_virtual_with_no_address():
    entry = json.loads(json.dumps(ENTRY))
    entry["event"]["location_type"] = "online"
    entry["event"]["geo_address_info"] = None
    entry["event"]["coordinate"] = None
    ev = event_from_json(SRC, entry)
    assert ev.raw.get("virtual") is True
    assert ev.address == "" and ev.lat is None


def test_unusable_entry_returns_none():
    assert event_from_json(SRC, {"event": {"api_id": "evt-x"}}) is None      # no title/start
    assert event_from_json(SRC, {}) is None


def test_real_fixture_parses():
    fix = os.path.join(os.path.dirname(__file__), "fixtures", "luma_get_items.json")
    with open(fix, encoding="utf-8") as f:
        entries = json.load(f)["entries"]
    evs = [event_from_json(SRC, e) for e in entries]
    evs = [e for e in evs if e is not None]
    assert len(evs) >= 1
    for e in evs:
        assert e.id.startswith("evt-")
        assert "T" in e.start and ("+" in e.start or "-" in e.start[10:])    # tz-aware
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_luma.py -q`
Expected: FAIL/ERROR with `ImportError: cannot import name 'event_from_json'`

- [ ] **Step 3: Add the mapper to `aggregator/fetchers/luma.py`**

Add below the existing code (keep `fetch_luma`/ICS import untouched in this task):

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from ..models import Event
from ..normalize import detect_topics
from ..provenance import prov_set


def _local_iso(utc_iso, tzname):
    """'2026-06-10T22:00:00.000Z' + IANA tz -> tz-aware local ISO (or None)."""
    if not utc_iso:
        return None
    dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    if tzname:
        try:
            dt = dt.astimezone(ZoneInfo(tzname))
        except KeyError:
            pass     # unknown tz -> keep UTC rather than drop the event
    return dt.isoformat()


def event_from_json(source: Source, entry: dict) -> Event | None:
    """Luma JSON event (get-items / discover entry) -> normalized Event.
    Returns None for unusable entries (no id/title/start), like parse_ics."""
    ev = entry.get("event") or {}
    eid = ev.get("api_id") or ""
    title = (ev.get("name") or "").strip()
    tzname = ev.get("timezone")
    start = _local_iso(ev.get("start_at"), tzname)
    if not eid or not title or not start:
        return None

    geo = ev.get("geo_address_info") or {}
    address = geo.get("full_address") or geo.get("address") or geo.get("city_state") or ""
    coord = ev.get("coordinate") or {}
    lat, lng = coord.get("latitude"), coord.get("longitude")

    out = Event(
        id=eid,
        title=title,
        start=start,
        end=_local_iso(ev.get("end_at"), tzname),
        tz=tzname,
        source=source.slug,
        source_url=f"https://lu.ma/{ev['url']}" if ev.get("url") else "",
        venue_name=address.split(",")[0].strip() if address else "",
        address=address,
        lat=float(lat) if lat is not None else None,
        lng=float(lng) if lng is not None else None,
        organizer=source.name,
        topics=detect_topics(title),
        raw={"calendar": source.name},
    )
    if ev.get("location_type") == "online":
        out.raw["virtual"] = True
    if address:
        prov_set(out, "location", "structured")
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_luma.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add tests/test_luma.py aggregator/fetchers/luma.py
git commit -m "feat(luma): JSON event mapper (structured coords, venue-local tz, virtual flag)"
```

---

### Task 3: Paginated fetchers `fetch_luma` (JSON) + `fetch_luma_discover` (TDD)

**Files:**
- Modify: `tests/test_luma.py` (append)
- Modify: `aggregator/fetchers/luma.py` (replace the ICS wrapper)

- [ ] **Step 1: Append the failing tests to `tests/test_luma.py`**

```python
import asyncio

from aggregator.fetchers.luma import fetch_luma, fetch_luma_discover

DISC = Source("luma-dc", "Luma DC (city-wide)", "luma-discover", 1, False,
              cal_id="discplace-AANPgOymN6bqFn8")


def _pages(responses):
    """get_json fake: pops canned (status, data) per call, records URLs."""
    calls = []

    async def get_json(url):
        calls.append(url)
        return responses.pop(0)

    return get_json, calls


def test_fetch_luma_paginates_until_has_more_false():
    p1 = {"entries": [ENTRY], "has_more": True, "next_cursor": "cur+1="}
    p2 = {"entries": [ENTRY], "has_more": False, "next_cursor": None}
    get_json, calls = _pages([(200, p1), (200, p2)])
    res = asyncio.run(fetch_luma(SRC, get_json=get_json))
    assert res.ok and len(res.events) == 2
    assert "calendar_api_id=cal-x" in calls[0] and "period=future" in calls[0]
    assert "pagination_cursor=cur%2B1%3D" in calls[1]          # cursor URL-quoted


def test_fetch_luma_http_error_quarantines():
    get_json, _ = _pages([(404, {})])
    res = asyncio.run(fetch_luma(SRC, get_json=get_json))
    assert not res.ok and res.status == 404 and res.reason == "HTTP 404"


def test_fetch_luma_empty_is_clean_empty():
    get_json, _ = _pages([(200, {"entries": [], "has_more": False})])
    res = asyncio.run(fetch_luma(SRC, get_json=get_json))
    assert res.error is None and res.status == 200 and res.events == []


def test_fetch_discover_hits_place_endpoint():
    get_json, calls = _pages([(200, {"entries": [ENTRY], "has_more": False})])
    res = asyncio.run(fetch_luma_discover(DISC, get_json=get_json))
    assert res.ok and len(res.events) == 1
    assert "discover/get-paginated-events" in calls[0]
    assert "discover_place_api_id=discplace-AANPgOymN6bqFn8" in calls[0]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_luma.py -q`
Expected: ERROR with `ImportError: cannot import name 'fetch_luma_discover'`

- [ ] **Step 3: Rewrite `aggregator/fetchers/luma.py`**

Replace the ENTIRE file with:

```python
"""Layer-1 adapter: Luma JSON APIs (per-calendar get-items + DC discover feed).

Replaced the per-calendar ICS subscription 2026-06-09: the JSON carries
structured coordinates, the venue IANA timezone, a virtual flag, and a direct
event URL that the ICS lacked (its DESCRIPTION is boilerplate), and the same
shape powers the city-wide discover source that catches DC events on calendars
we never curated. Unofficial API: any breakage quarantines cleanly and the ICS
fetcher is one git-revert away. `period=future` only -- past events archive on
the run after they happen (store + archive.ics retain them).
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from ..config import Source
from ..models import Event
from ..normalize import detect_topics
from ..provenance import prov_set
from .base import SourceResult

USER_AGENT = "dc-frontier-events/0.4 (+https://lu.ma)"
TIMEOUT = 30.0
API = "https://api.lu.ma"
PAGE_LIMIT = 50
MAX_PAGES = 10      # safety valve; both DC feeds are 1-2 pages today


def _local_iso(utc_iso, tzname):
    """'2026-06-10T22:00:00.000Z' + IANA tz -> tz-aware local ISO (or None)."""
    if not utc_iso:
        return None
    dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    if tzname:
        try:
            dt = dt.astimezone(ZoneInfo(tzname))
        except KeyError:
            pass     # unknown tz -> keep UTC rather than drop the event
    return dt.isoformat()


def event_from_json(source: Source, entry: dict) -> Event | None:
    """Luma JSON event (get-items / discover entry) -> normalized Event.
    Returns None for unusable entries (no id/title/start), like parse_ics."""
    ev = entry.get("event") or {}
    eid = ev.get("api_id") or ""
    title = (ev.get("name") or "").strip()
    tzname = ev.get("timezone")
    start = _local_iso(ev.get("start_at"), tzname)
    if not eid or not title or not start:
        return None

    geo = ev.get("geo_address_info") or {}
    address = geo.get("full_address") or geo.get("address") or geo.get("city_state") or ""
    coord = ev.get("coordinate") or {}
    lat, lng = coord.get("latitude"), coord.get("longitude")

    out = Event(
        id=eid,
        title=title,
        start=start,
        end=_local_iso(ev.get("end_at"), tzname),
        tz=tzname,
        source=source.slug,
        source_url=f"https://lu.ma/{ev['url']}" if ev.get("url") else "",
        venue_name=address.split(",")[0].strip() if address else "",
        address=address,
        lat=float(lat) if lat is not None else None,
        lng=float(lng) if lng is not None else None,
        organizer=source.name,
        topics=detect_topics(title),
        raw={"calendar": source.name},
    )
    if ev.get("location_type") == "online":
        out.raw["virtual"] = True
    if address:
        prov_set(out, "location", "structured")
    return out


async def _get_json(url: str) -> tuple[int, dict]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(headers=headers, timeout=TIMEOUT,
                                 follow_redirects=True) as client:
        r = await client.get(url)
        return r.status_code, (r.json() if r.status_code == 200 else {})


async def _fetch_pages(source: Source, base_url: str, get_json) -> SourceResult:
    events: list[Event] = []
    cursor = None
    for _ in range(MAX_PAGES):
        url = base_url + (f"&pagination_cursor={quote(cursor, safe='')}" if cursor else "")
        code, data = await get_json(url)
        if code != 200:
            return SourceResult(source, [], code, f"HTTP {code}")
        for entry in data.get("entries") or []:
            ev = event_from_json(source, entry)
            if ev is not None:
                events.append(ev)
        cursor = data.get("next_cursor")
        if not data.get("has_more") or not cursor:
            break
    return SourceResult(source, events, 200, None)


async def fetch_luma(source: Source, get_json=_get_json) -> SourceResult:
    url = (f"{API}/calendar/get-items?calendar_api_id={source.cal_id}"
           f"&period=future&pagination_limit={PAGE_LIMIT}")
    return await _fetch_pages(source, url, get_json)


async def fetch_luma_discover(source: Source, get_json=_get_json) -> SourceResult:
    url = (f"{API}/discover/get-paginated-events?discover_place_api_id={source.cal_id}"
           f"&pagination_limit={PAGE_LIMIT}")
    return await _fetch_pages(source, url, get_json)
```

- [ ] **Step 4: Run the luma tests, expect all pass**

Run: `python -m pytest tests/test_luma.py -q`
Expected: 10 passed

- [ ] **Step 5: Run the FULL suite (the ICS wrapper import just changed)**

Run: `python -m pytest -q`
Expected: all pass (392 + 10 new = 402). If `fetchers/__init__.py` import or any
test referencing the old Luma ICS path fails, fix forward in this task before
committing (expected: none — `fetch_luma` keeps its name and signature).

- [ ] **Step 6: Commit**

```bash
git add tests/test_luma.py aggregator/fetchers/luma.py
git commit -m "feat(luma): JSON fetchers with cursor pagination replace the ICS wrapper"
```

---

### Task 4: Wire config — `luma-dc` discover source, adapter registration, delete `ics_url`

**Files:**
- Modify: `aggregator/config.py` (LUMA_SOURCES + Source dataclass)
- Modify: `aggregator/fetchers/__init__.py` (ADAPTERS)
- Modify: `tests/test_luma.py` (append wiring tests)

- [ ] **Step 1: Append failing wiring tests to `tests/test_luma.py`**

```python
def test_luma_dc_discover_source_registered():
    from aggregator.config import SOURCES
    from aggregator.fetchers import ADAPTERS
    dc = next(s for s in SOURCES if s.slug == "luma-dc")
    assert dc.kind == "luma-discover"
    assert dc.cal_id == "discplace-AANPgOymN6bqFn8"
    assert dc.dc_curated is False                  # strict filter applies
    assert ADAPTERS["luma-discover"] is fetch_luma_discover


def test_ics_url_property_is_gone():
    assert not hasattr(SRC, "ics_url")
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_luma.py -q`
Expected: 2 failures (`StopIteration` / `KeyError: 'luma-discover'`, and
`ics_url` still present)

- [ ] **Step 3: Edit `aggregator/config.py`**

Delete the `ics_url` property (lines 24-26):

```python
    @property
    def ics_url(self) -> str:
        return f"https://api.lu.ma/ics/get?entity=calendar&id={self.cal_id}"
```

Update the `cal_id` field comment:

```python
    cal_id: str = ""   # luma calendar id ("cal-…") or discover place id ("discplace-…")
```

Update the LUMA_SOURCES header comment and append the discover source before the
closing bracket:

```python
# Layer 1 — Luma calendars + the DC city discover feed (api.lu.ma JSON;
# migrated off per-calendar ICS 2026-06-09, see docs/superpowers/specs/).
LUMA_SOURCES = [
    ...existing entries unchanged...
    # City-wide net: every public DC-area Luma event, whatever the calendar.
    # NOT dc_curated -- the strict topic/geo filter keeps only on-topic events.
    Source("luma-dc", "Luma DC (city-wide)", "luma-discover", 1, False,
           cal_id="discplace-AANPgOymN6bqFn8"),
]
```

- [ ] **Step 4: Edit `aggregator/fetchers/__init__.py`**

```python
from .luma import fetch_luma, fetch_luma_discover
```

and in ADAPTERS, after the `"luma"` line:

```python
    "luma-discover": fetch_luma_discover,
```

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: 404 passed (402 + 2). Also grep for orphans:
`grep -rn "ics_url" aggregator/ tests/` → no hits.

- [ ] **Step 6: Commit**

```bash
git add aggregator/config.py aggregator/fetchers/__init__.py tests/test_luma.py
git commit -m "feat(sources): luma-dc city-wide discover source; drop Source.ics_url"
```

---

### Task 5: Live verification + deploy

**Files:** none new (ops)

- [ ] **Step 1: Live-check the new source locally**

Run: `python tools/live_check.py luma-dc` and `python tools/live_check.py DC2`
Expected: both fetch with status 200; luma-dc shows the city feed with only
on-topic DC events kept; DC2 shows its upcoming events (~4 today).

- [ ] **Step 2: Deploy to the box**

```bash
tar -czf - aggregator/config.py aggregator/fetchers/luma.py aggregator/fetchers/__init__.py tests/test_luma.py tests/fixtures/luma_get_items.json tests/fixtures/luma_discover.json | ssh root@37.27.242.32 "cd /opt/dc-frontier-events && tar -xzf - && chown -R emersus:emersus aggregator tests"
```

- [ ] **Step 3: Trigger a build and read the summary**

```bash
ssh root@37.27.242.32 "systemctl start dc-frontier-events.service && journalctl -u dc-frontier-events.service --since '2 min ago' --no-pager | grep -E 'sources:|quarantined|kept after|gone-from|emitted'"
```

Expected: `luma-dc` present with events; Luma calendar counts drop to
upcoming-only (DC2 ~4, aic-washington ~upcoming subset); one-time large
`gone-from-sources` spike (past Luma events archiving); DCtechevents still
quarantined `empty`; no Luma source quarantined with an HTTP error.

- [ ] **Step 4: Verify the public feed**

```bash
curl -s https://events.emersus.ai/events.ics | grep -c "BEGIN:VEVENT"
```

Expected: count matches the run's `emitted: events.ics=N`.

- [ ] **Step 5: Push**

```bash
git push && gh run watch --exit-status $(gh run list --limit 1 --json databaseId --jq '.[0].databaseId')
```

Expected: CI green.
