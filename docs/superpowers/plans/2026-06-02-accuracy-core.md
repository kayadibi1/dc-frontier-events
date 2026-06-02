# Accuracy Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make future scraper runs more accurate by sourcing event data from authoritative schema.org markup and pruning/downgrading fields that fail cross-checks, rather than emitting plausible-but-wrong values.

**Architecture:** A new `structured.py` reads schema.org `Event` JSON-LD from Layer-2 detail pages (CSIS today); `enrich.py` prefers it over heuristics and reconciles CSIS naive-UTC times. A new two-phase `validate.py` gate runs offline cleanups before the filter and coordinate cross-checks after geocode, returning `(clean, dropped)`. `pipeline.py` is reordered so `scrub_far_geo` stays before geocode, validation runs at both points, the validated set is stored, and scoring happens after final coordinates.

**Tech Stack:** Python 3.14, selectolax, pytest. No new dependencies. (Revised after Codex round 1.)

**Spec:** `docs/superpowers/specs/2026-06-02-accuracy-core-design.md`

**Execution note (git):** Before Task 1:
```bash
git switch -c accuracy-core
git add -A && git commit -m "chore: pending B1-B5 fixes + accuracy-core spec & plan"
```
Run all commands through the Bash tool (git-bash); `python -m pytest` and `rm -rf` work there.

---

### Task 1: `structured.py` — schema.org Event extraction

**Files:** Create `aggregator/structured.py`, `tests/fixtures/csis_event_jsonld.html`, `tests/test_structured.py`

- [ ] **Step 1: Save a real-shaped CSIS fixture** — `tests/fixtures/csis_event_jsonld.html`:

```html
<!doctype html><html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Event",
 "name":"Data Centers, AI, and the Future of U.S. Strategic Competitiveness",
 "startDate":"2026-06-04T14:30:00","endDate":"2026-06-04T15:30:00",
 "eventAttendanceMode":"https://schema.org/OnlineEventAttendanceMode",
 "location":{"@type":"VirtualLocation",
   "url":"https://www.csis.org/events/data-centers-ai-and-future-us-strategic-competitiveness"}}
</script></head><body><h1>CSIS</h1></body></html>
```

- [ ] **Step 2: Write failing tests** — `tests/test_structured.py`:

```python
from aggregator.structured import extract_structured

CSIS = open("tests/fixtures/csis_event_jsonld.html", encoding="utf-8").read()

PLACE = """<script type="application/ld+json">
{"@type":"Event","name":"Panel","startDate":"2026-06-10T10:00:00-04:00",
 "endDate":"2026-06-10T11:00:00-04:00",
 "location":{"@type":"Place","name":"Saul Auditorium","address":{"@type":"PostalAddress",
   "streetAddress":"1775 Massachusetts Ave NW","addressLocality":"Washington",
   "addressRegion":"DC","postalCode":"20036"}},
 "performer":[{"@type":"Person","name":"Neil Thompson"},{"@type":"Person","name":"Sanjay Patnaik"}]}
</script>"""

HYBRID = """<script type="application/ld+json">
{"@type":"Event","name":"Hybrid","startDate":"2026-06-10T10:00:00-04:00",
 "eventAttendanceMode":"https://schema.org/MixedEventAttendanceMode",
 "location":[{"@type":"Place","name":"HQ","address":{"@type":"PostalAddress",
   "streetAddress":"1400 L St NW","addressLocality":"Washington","addressRegion":"DC","postalCode":"20005"}},
   {"@type":"VirtualLocation","url":"https://x"}]}
</script>"""

ONLINE_MODE = """<script type="application/ld+json">
{"@type":"Event","name":"Webinar","startDate":"2026-06-10T10:00:00",
 "eventAttendanceMode":"https://schema.org/OnlineEventAttendanceMode"}
</script>"""

GRAPH = """<script type="application/ld+json">
{"@graph":[{"@type":"WebPage"},{"@type":["Event"],"name":"G","startDate":"2026-07-01"}]}
</script>"""


def test_csis_virtual_naive_start():
    out = extract_structured(CSIS)
    assert out["virtual"] is True
    assert out["start"] == "2026-06-04T14:30:00"
    assert out["end"] == "2026-06-04T15:30:00"
    assert "address" not in out and "venue_name" not in out


def test_place_offset_aware_with_address_and_speakers():
    out = extract_structured(PLACE)
    assert out["start"] == "2026-06-10T10:00:00-04:00"
    assert out["venue_name"] == "Saul Auditorium"
    assert "1775 Massachusetts Ave NW" in out["address"] and "20036" in out["address"]
    assert out["speakers"] == ["Neil Thompson", "Sanjay Patnaik"]
    assert "virtual" not in out


def test_hybrid_keeps_physical_address():
    out = extract_structured(HYBRID)
    assert "1400 L St NW" in out["address"]
    assert out.get("attendance_mode") == "mixed"
    assert out.get("virtual") is not True


def test_online_attendance_mode_without_virtuallocation():
    out = extract_structured(ONLINE_MODE)
    assert out["virtual"] is True and out.get("attendance_mode") == "online"


def test_graph_form_and_type_list():
    assert extract_structured(GRAPH)["start"] == "2026-07-01"


def test_malformed_and_missing_return_empty():
    assert extract_structured('<script type="application/ld+json">{bad json}</script>') == {}
    assert extract_structured("<p>no markup</p>") == {}
    assert extract_structured('<script type="application/ld+json">{"@type":"WebPage"}</script>') == {}


def test_og_meta_never_sets_event_fields():
    html = ('<meta property="og:title" content="X">'
            '<meta property="article:published_time" content="2020-01-01T00:00:00Z">')
    assert extract_structured(html) == {}
```

- [ ] **Step 3: Run, verify fail** — `python -m pytest tests/test_structured.py -q` → FAIL (`No module named 'aggregator.structured'`)

- [ ] **Step 4: Implement `aggregator/structured.py`**

```python
"""Authoritative event data from a detail page's schema.org markup.

Some Layer-2 detail pages embed a schema.org `Event` as JSON-LD. When present it
is authoritative for venue, virtual-vs-physical, and times. `extract_structured`
returns ONLY fields it confidently finds. JSON-LD `Event` is the ONLY source
allowed to set start/end/address; generic page metadata (og:*,
article:published_time, datePublished) is ignored.
"""
from __future__ import annotations

import json

from selectolax.parser import HTMLParser


def _iter_jsonld(tree: HTMLParser):
    for node in tree.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(node.text() or "")
        except (ValueError, TypeError):
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                if isinstance(item.get("@graph"), list):
                    stack.extend(item["@graph"])
                yield item


def _types(node: dict) -> str:
    t = node.get("@type")
    return " ".join(t) if isinstance(t, list) else str(t or "")


def _format_address(postal) -> str:
    if isinstance(postal, str):
        return postal.strip()
    if not isinstance(postal, dict):
        return ""
    parts = [postal.get(k) for k in
             ("streetAddress", "addressLocality", "addressRegion", "postalCode")]
    return ", ".join(p.strip() for p in parts if isinstance(p, str) and p.strip())


def _parse_location(loc) -> dict:
    items = loc if isinstance(loc, list) else [loc]
    has_place = has_virtual = False
    venue_name = address = ""
    for it in items:
        if not isinstance(it, dict):
            continue
        ts = _types(it)
        if "VirtualLocation" in ts:
            has_virtual = True
        elif "Place" in ts or it.get("address"):
            has_place = True
            venue_name = venue_name or (it.get("name") or "").strip()
            address = address or _format_address(it.get("address") or it)
    out: dict = {}
    if venue_name:
        out["venue_name"] = venue_name
    if address:
        out["address"] = address
    if has_virtual and has_place:
        out["attendance_mode"] = "mixed"
    elif has_virtual:
        out["virtual"] = True
        out["attendance_mode"] = "online"
    out["_has_place"] = has_place      # internal hint for attendance-mode refinement
    return out


def extract_structured(html: str) -> dict:
    tree = HTMLParser(html or "")
    node = next((n for n in _iter_jsonld(tree) if "Event" in _types(n)), None)
    if node is None:
        return {}
    out: dict = {}
    for key, prop in (("start", "startDate"), ("end", "endDate")):
        v = node.get(prop)
        if isinstance(v, str) and v.strip():
            out[key] = v.strip()
    loc = node.get("location")
    has_place = False
    if loc is not None:
        parsed = _parse_location(loc)
        has_place = parsed.pop("_has_place", False)
        out.update(parsed)
    # eventAttendanceMode refines virtual even without a VirtualLocation node.
    mode = node.get("eventAttendanceMode")
    if isinstance(mode, str):
        if "Online" in mode and not has_place and "virtual" not in out:
            out["virtual"] = True
            out["attendance_mode"] = "online"
        elif "Mixed" in mode and has_place:
            out["attendance_mode"] = "mixed"
    perf = node.get("performer")
    if perf is not None:
        names = []
        for p in (perf if isinstance(perf, list) else [perf]):
            nm = p.get("name") if isinstance(p, dict) else (p if isinstance(p, str) else None)
            if isinstance(nm, str) and nm.strip():
                names.append(nm.strip())
        if names:
            out["speakers"] = names
    return out
```

- [ ] **Step 5: Run, verify pass; commit** — `python -m pytest tests/test_structured.py -q` → PASS (7)
```bash
git add aggregator/structured.py tests/test_structured.py tests/fixtures/csis_event_jsonld.html
git commit -m "feat(structured): extract schema.org Event JSON-LD (venue/virtual/times/speakers)"
```

---

### Task 2: `enrich.py` — prefer structured data; record virtual state

**Files:** Modify `aggregator/enrich.py`; append `tests/test_enrich.py`

- [ ] **Step 1: Failing tests** (append):

```python
def test_enrich_structured_location_and_virtual_win():
    ev = Event(id="csis-z", title="AI", start="2026-06-04", source="csis",
               source_url="https://www.csis.org/events/z")

    async def fake_fetch(url, kind):
        return ('<script type="application/ld+json">{"@type":"Event",'
                '"startDate":"2026-06-04T14:30:00","location":{"@type":"VirtualLocation","url":"x"}}'
                '</script>')

    asyncio.run(enrich_layer2([ev], {"csis": 2}, fake_fetch))
    assert ev.raw.get("virtual") is True
    assert ev.address == ""


def test_enrich_structured_address_overrides_hq():
    ev = Event(id="brk-z", title="AI", start="2026-06-10", source="brookings",
               source_url="https://www.brookings.edu/events/z")

    async def fake_fetch(url, kind):
        return ('<script type="application/ld+json">{"@type":"Event",'
                '"location":{"@type":"Place","name":"Saul Auditorium","address":'
                '{"@type":"PostalAddress","streetAddress":"1775 Massachusetts Ave NW",'
                '"addressLocality":"Washington","addressRegion":"DC","postalCode":"20036"}}}</script>')

    asyncio.run(enrich_layer2([ev], {"brookings": 2}, fake_fetch))
    assert "1775 Massachusetts Ave NW" in ev.address
    assert ev.venue_name == "Saul Auditorium"
    assert ev.address != SOURCE_HQ["brookings"]
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_enrich.py -k structured -q` → FAIL

- [ ] **Step 3: Edit `enrich.py`**

Add imports (top, with the other imports):
```python
from datetime import datetime, timezone
from .structured import extract_structured
```

In `enrich_layer2`'s inner `one()`, **replace from the line `ev.speakers = extract_speakers(html or "")` through the existing `return 1 if (...) else 0`** with:

```python
        st = extract_structured(html or "")

        sp = [s for s in st.get("speakers", []) if _looks_like_name(s)]
        ev.speakers = sp or extract_speakers(html or "")

        added_desc = False
        if not ev.description:
            ev.description = extract_description(html or "")
            added_desc = bool(ev.description)

        if st.get("virtual"):
            virtual = True
        elif "attendance_mode" in st:        # "mixed" -> not pure virtual
            virtual = False
        else:
            virtual = _is_virtual_only(html or "")
        if virtual:
            ev.raw["virtual"] = True
        if st.get("attendance_mode"):
            ev.raw["attendance_mode"] = st["attendance_mode"]

        added_loc = False
        if st.get("venue_name") and not ev.venue_name:
            ev.venue_name = st["venue_name"]
        if not ev.address:
            scraped = st.get("address") or extract_location(html or "")
            if scraped:
                ev.address = scraped
            elif not virtual:
                ev.address = SOURCE_HQ.get(ev.source, "")
            added_loc = bool(ev.address)

        _reconcile_time(ev, st)
        return 1 if (ev.speakers or added_desc or added_loc) else 0
```

Add a temporary stub (replaced in Task 3), placed at module level above `enrich_layer2`:
```python
def _reconcile_time(ev: Event, st: dict) -> None:
    return None
```

- [ ] **Step 4: Run, verify pass** — `python -m pytest tests/test_enrich.py -q` → PASS

- [ ] **Step 5: Commit**
```bash
git add aggregator/enrich.py tests/test_enrich.py
git commit -m "feat(enrich): prefer structured Event data; record raw[virtual]/attendance_mode"
```

---

### Task 3: `enrich.py` — CSIS naive-UTC reconciliation (start AND end)

**Files:** Modify `aggregator/enrich.py` (replace the `_reconcile_time` stub); append `tests/test_enrich.py`

- [ ] **Step 1: Failing tests** (append):

```python
def test_reconcile_csis_naive_agrees_sets_end():
    from aggregator.enrich import _reconcile_time
    ev = Event(id="csis-a", title="A", start="2026-06-04T10:30:00-04:00", tz="EDT",
               source="csis", end=None)
    _reconcile_time(ev, {"start": "2026-06-04T14:30:00", "end": "2026-06-04T15:30:00"})
    assert ev.start == "2026-06-04T10:30:00-04:00"          # listing kept
    assert ev.end == "2026-06-04T11:30:00-04:00"            # structured end -> listing offset
    assert ev.raw.get("start_conflict") is not True


def test_reconcile_csis_naive_conflict_downgrades():
    from aggregator.enrich import _reconcile_time
    ev = Event(id="csis-b", title="B", start="2026-06-04T10:30:00-04:00", tz="EDT",
               source="csis", end="2026-06-04T11:30:00-04:00")
    _reconcile_time(ev, {"start": "2026-06-04T20:00:00"})
    assert ev.start == "2026-06-04" and ev.end == "2026-06-04" and ev.tz is None
    assert ev.raw.get("start_conflict") is True


def test_reconcile_offset_aware_structured_wins():
    from aggregator.enrich import _reconcile_time
    ev = Event(id="x-c", title="C", start="2026-06-10", source="brookings")
    _reconcile_time(ev, {"start": "2026-06-10T09:00:00-04:00", "end": "2026-06-10T10:00:00-04:00"})
    assert ev.start == "2026-06-10T09:00:00-04:00" and ev.end == "2026-06-10T10:00:00-04:00"
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_enrich.py -k reconcile -q` → FAIL

- [ ] **Step 3: Replace the stub**

```python
def _reconcile_time(ev: Event, st: dict) -> None:
    """Apply a structured start/end over the listing's, honoring offset-awareness.
    Offset-aware structured time wins. A naive structured time is trusted only for
    CSIS (its JSON-LD emits naive UTC): cross-check the start against the
    offset-aware listing; on agreement also adopt the structured end (converted to
    the listing's offset); on conflict downgrade start+end+tz to date-only."""
    s = st.get("start")
    if not s:
        return
    try:
        sdt = datetime.fromisoformat(s)
    except ValueError:
        return
    ev.raw["start_structured"] = s
    if sdt.tzinfo is not None:                        # authoritative
        ev.start = s
        if st.get("end"):
            ev.end = st["end"]
        return
    if ev.source != "csis" or not ev.start:
        return
    try:
        listing = datetime.fromisoformat(ev.start)
    except ValueError:
        return
    if listing.tzinfo is None:
        return
    struct_utc = sdt.replace(tzinfo=timezone.utc)     # CSIS naive == UTC
    if struct_utc != listing.astimezone(timezone.utc):
        ev.raw["start_conflict"] = True
        ev.start = ev.start[:10]
        ev.end = ev.end[:10] if ev.end else ev.end
        ev.tz = None
        return
    # agreement: adopt the structured end, expressed in the listing's offset
    end_s = st.get("end")
    if end_s:
        try:
            edt = datetime.fromisoformat(end_s).replace(tzinfo=timezone.utc)
            ev.end = edt.astimezone(listing.tzinfo).isoformat()
        except ValueError:
            pass
```

- [ ] **Step 4: Run, verify pass** — `python -m pytest tests/test_enrich.py -q` → PASS

- [ ] **Step 5: Commit**
```bash
git add aggregator/enrich.py tests/test_enrich.py
git commit -m "feat(enrich): CSIS naive-UTC reconciliation (start+end, conflict downgrade)"
```

---

### Task 4: `validate.py` — `validate_pre_filter`

**Files:** Create `aggregator/validate.py`, `tests/test_validate.py`

- [ ] **Step 1: Failing tests** — `tests/test_validate.py`:

```python
from aggregator.models import Event
from aggregator.validate import validate_pre_filter

T = "2026-06-02"
NAMES = ["Alpha Bravo", "Charlie Delta", "Echo Foxtrot", "Golf Hotel", "India Juliet",
         "Kilo Lima", "Mike November", "Oscar Papa", "Quebec Romeo", "Sierra Tango",
         "Uniform Victor", "Whiskey Xray", "Yankee Zulu"]   # 13 digit-free names


def _ev(**kw):
    kw.setdefault("title", "x"); kw.setdefault("source", "csis"); kw.setdefault("start", "2026-06-10")
    return Event(id=kw.pop("id", "e1"), **kw)


def test_pre_excludes_implausible_date():
    clean, dropped = validate_pre_filter([_ev(start="0202-01-01")], T)
    assert clean == [] and dropped[0][1] == "date"


def test_pre_downgrades_timed_without_tz():
    ev = _ev(start="2026-06-10T11:00:00", end="2026-06-10T12:00:00", tz=None)
    clean, dropped = validate_pre_filter([ev], T)
    assert ev.start == "2026-06-10" and ev.end == "2026-06-10"
    assert any(d[1] == "time" for d in dropped)


def test_pre_drops_overlong_speaker_list_wholesale():
    ev = _ev(speakers=list(NAMES))                 # 13 valid names -> over MAX
    validate_pre_filter([ev], T)
    assert ev.speakers == []


def test_pre_removes_junk_speakers_keeps_real():
    ev = _ev(speakers=["EDT Brought", "Arun Gupta"])
    validate_pre_filter([ev], T)
    assert ev.speakers == ["Arun Gupta"]


def test_pre_clears_address_for_pure_virtual():
    ev = _ev(address="CSIS, 1616 Rhode Island Ave NW, Washington, DC 20036",
             raw={"virtual": True})
    validate_pre_filter([ev], T)
    assert ev.address == ""


def test_pre_keeps_zipless_address():
    ev = _ev(address="Marvin Center, Washington, DC")
    validate_pre_filter([ev], T)
    assert ev.address == "Marvin Center, Washington, DC"     # NOT nulled pre-filter
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_validate.py -q` → FAIL (no module)

- [ ] **Step 3: Implement `validate.py` (pre-filter half)**

```python
"""Two-phase validation gate. Prefer omitting/downgrading a field to emitting a
wrong value. `validate_pre_filter` cleans fields the relevance filter consumes (so
it runs BEFORE apply_filters, which is not idempotent). `validate_post_geocode`
(below) does coordinate cross-checks AFTER geocode. Each returns (clean, dropped),
dropped = list of (event_id, field, reason). `today_iso` is injected (never
wall-clock) for deterministic tests / --today runs.
"""
from __future__ import annotations

from datetime import date, datetime

from .enrich import _looks_like_name
from .models import Event

DATE_WINDOW_YEARS = 3
MAX_SPEAKERS = 12


def _date_of(start: str | None):
    if not start:
        return None
    try:
        return date.fromisoformat(start[:10])
    except ValueError:
        return None


def _is_timed(start: str | None) -> bool:
    return bool(start) and "T" in start


def _tzinfo_of(start: str | None):
    try:
        return datetime.fromisoformat(start).tzinfo if start else None
    except ValueError:
        return None


def validate_pre_filter(events: list[Event], today_iso: str) -> tuple[list[Event], list]:
    today = date.fromisoformat(today_iso)
    lo, hi = date(today.year - DATE_WINDOW_YEARS, 1, 1), date(today.year + DATE_WINDOW_YEARS, 12, 31)
    clean: list[Event] = []
    dropped: list = []
    for ev in events:
        d = _date_of(ev.start)
        if d is None or not (lo <= d <= hi):
            dropped.append((ev.id, "date", f"implausible:{ev.start}"))
            continue
        if _is_timed(ev.start) and _tzinfo_of(ev.start) is None:
            dropped.append((ev.id, "time", "timed-no-tz"))
            ev.start = ev.start[:10]
            if ev.end:
                ev.end = ev.end[:10]
            ev.tz = None
        if ev.speakers:
            cleaned = [s for s in ev.speakers if _looks_like_name(s)]
            if len(cleaned) > MAX_SPEAKERS:
                dropped.append((ev.id, "speakers", "over-limit"))
                cleaned = []
            elif len(cleaned) != len(ev.speakers):
                dropped.append((ev.id, "speakers", "junk-removed"))
            ev.speakers = cleaned
        # A pure-virtual event must not carry a physical-venue (HQ) fallback.
        # NOTE: no generic junk-address nulling here -- that would erase valid
        # ZIP-less venues (e.g. "Marvin Center, Washington, DC") and is handled,
        # geocode-informed, in validate_post_geocode.
        if ev.raw.get("virtual") and ev.address:
            dropped.append((ev.id, "address", "virtual-cleared"))
            ev.address = ""
        clean.append(ev)
    return clean, dropped
```

- [ ] **Step 4: Run, verify pass** — `python -m pytest tests/test_validate.py -q` → PASS (6)

- [ ] **Step 5: Commit**
```bash
git add aggregator/validate.py tests/test_validate.py
git commit -m "feat(validate): pre-filter cleanups (date, tz, speakers, pure-virtual address)"
```

---

### Task 5: `validate.py` — `validate_post_geocode`

**Files:** Modify `aggregator/validate.py`; append `tests/test_validate.py`

- [ ] **Step 1: Failing tests** (append):

```python
from aggregator.validate import validate_post_geocode

DC = (38.90, -77.04)


def test_post_nulls_out_of_bbox(tmp_path):
    ev = _ev(lat=-8.5, lng=179.2)
    validate_post_geocode([ev], T, query=None, cache_path=str(tmp_path / "gc.json"))
    assert ev.lat is None and ev.lng is None


def test_post_geo_far_from_address_pruned(tmp_path):
    ev = _ev(lat=DC[0], lng=DC[1], address="123 Far Away Rd, Washington, DC 20001")
    validate_post_geocode([ev], T, query=lambda a: (38.99, -77.20),
                          cache_path=str(tmp_path / "gc.json"), sleep=lambda *_: None)
    assert ev.lat is None


def test_post_geo_near_address_kept(tmp_path):
    ev = _ev(lat=DC[0], lng=DC[1], address="123 Near St, Washington, DC 20001")
    validate_post_geocode([ev], T, query=lambda a: (38.901, -77.041),
                          cache_path=str(tmp_path / "gc.json"), sleep=lambda *_: None)
    assert ev.lat == DC[0]


def test_post_geocoder_exception_does_not_prune_pin(tmp_path):
    def boom(a): raise OSError("down")
    ev = _ev(lat=DC[0], lng=DC[1], address="123 Some St, Washington, DC 20001")
    validate_post_geocode([ev], T, query=boom, cache_path=str(tmp_path / "gc.json"),
                          sleep=lambda *_: None)
    assert ev.lat == DC[0]


def test_post_geocoder_exception_keeps_zipless_address(tmp_path):
    def boom(a): raise OSError("down")
    ev = _ev(address="Some Hall, Washington, DC", lat=None, lng=None)
    clean, _ = validate_post_geocode([ev], T, query=boom, cache_path=str(tmp_path / "gc.json"),
                                     sleep=lambda *_: None)
    assert ev.address == "Some Hall, Washington, DC"


def test_post_definitive_miss_nulls_zipless_address(tmp_path):
    ev = _ev(source="aic-washington", address="Nowhere Plaza", lat=None, lng=None, title="x")
    validate_post_geocode([ev], T, query=lambda a: None,
                          cache_path=str(tmp_path / "gc.json"), sleep=lambda *_: None)
    assert ev.address == ""


def test_post_zipless_address_kept_when_no_geocoder(tmp_path):
    ev = _ev(address="Marvin Center, Washington, DC", lat=None, lng=None)
    validate_post_geocode([ev], T, query=None, cache_path=str(tmp_path / "gc.json"))
    assert ev.address == "Marvin Center, Washington, DC"


def test_post_dc_recheck_excludes_nonDC_after_address_nulled(tmp_path):
    # aic-washington is NOT dc_curated (global feed) -> excluded once geo/address gone
    ev = _ev(source="aic-washington", address="Nowhere Plaza", raw={"location": "Nowhere Plaza"},
             lat=None, lng=None, title="AI talk")
    clean, dropped = validate_post_geocode([ev], T, query=lambda a: None,
                                           cache_path=str(tmp_path / "gc.json"), sleep=lambda *_: None)
    assert clean == [] and any(d[1] == "dc" for d in dropped)
```

(Before relying on `aic-washington` being non-curated, confirm: `python -c "from aggregator.filter import _DC_CURATED; print('aic-washington' in _DC_CURATED)"` → must print `False`. If it prints `True`, pick another non-curated source from `aggregator/config.py`.)

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_validate.py -k post -q` → FAIL (`cannot import name`)

- [ ] **Step 3: Implement the post-geocode half** (append to `validate.py`)

Add imports at top:
```python
import time
from .config import DC_BBOX, SOURCE_HQ
from .filter import is_dc_relevant
from .geocode import _address_variants, _norm, load_cache, save_cache, nominatim_query
from .rank import _haversine_km
```
Add code:
```python
STREET_KM = 2.0
VENUE_KM = 10.0
_MIN_INTERVAL_S = 1.1


def _in_bbox(lat: float, lng: float) -> bool:
    b = DC_BBOX
    return b["lat_min"] <= lat <= b["lat_max"] and b["lng_min"] <= lng <= b["lng_max"]


def _has_street_number(addr: str) -> bool:
    return any(part[:1].isdigit() for part in addr.split())


def _has_zip(addr: str) -> bool:
    tail = addr.split(",")[-1]
    return any(ch.isdigit() for ch in tail)


def validate_post_geocode(events: list[Event], today_iso: str, query=None,
                          cache_path: str | None = None, sleep=time.sleep) -> tuple[list[Event], list]:
    cache = load_cache(cache_path) if (query is not None and cache_path) else {}
    state = {"queried": False, "dirty": False}

    def truth(address: str):
        """(ok, coords): ok=False on a transient exception (NOT evidence);
        ok=True with coords or None on a definitive hit/miss. Cached + throttled."""
        key = _norm(address)
        if key in cache:
            return True, cache[key]
        result = None
        try:
            for variant in _address_variants(address):
                if state["queried"]:
                    sleep(_MIN_INTERVAL_S)
                state["queried"] = True
                result = query(variant)
                if result:
                    break
        except Exception:
            return False, None
        cache[key] = list(result) if result else None
        state["dirty"] = True
        return True, cache[key]

    clean: list[Event] = []
    dropped: list = []
    for ev in events:
        if ev.lat is not None and ev.lng is not None and not _in_bbox(ev.lat, ev.lng):
            dropped.append((ev.id, "geo", "out-of-bbox"))
            ev.lat = ev.lng = None
        if ev.lat is not None and ev.lng is not None and ev.address and query is not None:
            ok, coords = truth(ev.address)
            if ok and coords:
                km = _haversine_km(ev.lat, ev.lng, coords[0], coords[1])
                if km > (STREET_KM if _has_street_number(ev.address) else VENUE_KM):
                    dropped.append((ev.id, "geo", f"far-from-address:{km:.1f}km"))
                    ev.lat = ev.lng = None
        if ev.address and not _address_ok(ev, query, truth):
            dropped.append((ev.id, "address", "unverified"))
            ev.raw.pop("location", None)        # mask stale text for the DC recheck
            ev.address = ""
        if not is_dc_relevant(ev):
            dropped.append((ev.id, "dc", "not-dc-after-validation"))
            continue
        clean.append(ev)
    if state["dirty"] and cache_path:
        try:
            save_cache(cache_path, cache)
        except OSError:
            pass
    return clean, dropped


def _address_ok(ev: Event, query, truth) -> bool:
    addr = ev.address
    if _has_zip(addr):
        return True
    if addr in SOURCE_HQ.values():
        return True
    if ev.lat is not None and ev.lng is not None:
        return True
    if query is None:
        return True                              # can't verify offline -> keep
    ok, coords = truth(addr)
    if not ok:
        return True                              # transient failure is not evidence
    return coords is not None                    # definitive miss -> unverified
```

- [ ] **Step 4: Run, verify pass** — `python -m pytest tests/test_validate.py -q` → PASS (14)

- [ ] **Step 5: Commit**
```bash
git add aggregator/validate.py tests/test_validate.py
git commit -m "feat(validate): post-geocode bbox/geo-vs-address/address checks + DC recheck"
```

---

### Task 6: `pipeline.py` — wire both phases in corrected order

**Files:** Modify `aggregator/pipeline.py`; create `tests/test_pipeline_validate.py`

- [ ] **Step 1: Write a real `pipeline.run` integration test** — `tests/test_pipeline_validate.py`:

```python
import json

import aggregator.pipeline as pl
from aggregator.config import Source
from aggregator.fetchers.base import SourceResult
from aggregator.models import Event


def test_pipeline_excludes_garbage_date_end_to_end(tmp_path, monkeypatch):
    src = Source("DC2", "DC2", "luma", 1, True, url="x")
    good = Event(id="g", title="AI workshop", start="2026-06-10", source="DC2",
                 lat=38.9, lng=-77.04, topics=["ai"])
    bad = Event(id="b", title="AI", start="0202-01-01", source="DC2", topics=["ai"])

    async def fake_gather(sources):
        return [SourceResult(src, [good, bad], 200, None)]

    monkeypatch.setattr(pl, "gather_all", fake_gather)
    monkeypatch.setattr(pl, "deliver", lambda *a, **k: ("dry-run", "test"))
    pl.run(out_dir=str(tmp_path / "o"), db_path=str(tmp_path / "db.sqlite"),
           today="2026-06-02", enrich=False)
    recs = json.load(open(tmp_path / "o" / "events.json", encoding="utf-8"))
    ids = {r["id"] for r in recs}
    assert "g" in ids and "b" not in ids          # garbage date excluded end-to-end
    assert all(r.get("lat") is None or -77.6 <= r["lng"] <= -76.8 for r in recs)  # no ocean pins
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_pipeline_validate.py -q`
Expected: FAIL — currently the garbage-date event is NOT excluded (no validation wired).

- [ ] **Step 3: Edit `pipeline.py`**

(a) Imports — change the geocode import line and add validate:
```python
from .geocode import DEFAULT_CACHE, geocode_events, nominatim_query, scrub_far_geo
from .validate import validate_pre_filter, validate_post_geocode
```

(b) Insert pre-filter validation right AFTER the enrich block and BEFORE `deduped, removed = dedupe(raw_events)`:
```python
    raw_events, pre_dropped = validate_pre_filter(raw_events, today)
    print(f"[validate] pre-filter: excluded "
          f"{sum(1 for d in pre_dropped if d[1] == 'date')}, "
          f"cleaned {len(pre_dropped)} field(s)")
```

(c) Read the current section from `deduped, removed = dedupe(raw_events)` through the
geocode block (the part that does dedupe → filter → the early store block →
`emitted = sorted(...)` → score loop → `scrub_far_geo` → geocode). **Replace that
entire section** with this exact end-state:

```python
    deduped, removed = dedupe(raw_events)
    kept, fstats = apply_filters(deduped)

    store = open_store(db_path)
    prior_ids = store.existing_ids()          # ids known before this run -> new diff
    store.close()

    # Scrub junk feed GEO BEFORE geocode so a real DC address can re-pin (B2).
    scrub_far_geo(kept)
    if enrich:
        n_geo = geocode_events(kept)
        print(f"[geocode] added coordinates to {n_geo} event(s)")
    clean, post_dropped = validate_post_geocode(
        kept, today, query=nominatim_query if enrich else None,
        cache_path=DEFAULT_CACHE if enrich else None)
    print(f"[validate] post-geocode: dropped {len(post_dropped)} field(s); "
          f"kept {len(clean)}/{len(kept)}")

    # Persist the VALIDATED active set; the store is the durable archive.
    store = open_store(db_path)
    store.upsert_many(clean)
    archived_total = store.mark_archived({e.id for e in clean})
    cutoff = (date.fromisoformat(today) - timedelta(days=730)).isoformat()
    pruned = store.prune(cutoff)
    roundtrip = store.all_events()
    store_total = store.count()
    store.close()
    assert len(roundtrip) >= len(clean), "storage round-trip lost rows"
    gone = sorted(set(prior_ids) - {e.id for e in clean})

    emitted = sorted(clean, key=lambda e: e.start or "")
    for e in emitted:
        e.raw["score"] = score_event(e, today)   # ephemeral; AFTER store
```

(d) In the `summary` dict, change `"kept_after_filter": len(kept)` to
`"kept_after_filter": len(clean)` and add `"pre_excluded": sum(1 for d in pre_dropped if d[1]=="date")` and `"post_excluded": sum(1 for d in post_dropped if d[1]=="dc")`. In `_print_summary`, add a line:
`print(f"validated:         pre-excluded={s['pre_excluded']} post-excluded={s['post_excluded']}")`.
Leave the existing `big`, `upcoming`, `top`, `new_events`, `big_in_dc` derivations as-is — they already read `emitted`/`clean`.

- [ ] **Step 4: Run the integration test + full suite + live smoke**

Run: `python -m pytest tests/test_pipeline_validate.py -q` → PASS
Run: `python -m pytest -q` → PASS (all)
Run: `python -m aggregator --out out_e2e --db data/e2e.db --today 2026-06-02`
Expected: `[validate] pre-filter ...` + `[validate] post-geocode ...` lines; RUN SUMMARY; no crash.

- [ ] **Step 5: Commit**
```bash
git add aggregator/pipeline.py tests/test_pipeline_validate.py
git commit -m "feat(pipeline): two-phase validation; store-before-score; scrub-before-geocode"
```

---

### Task 7: Full verification (suite + live gate-check)

**Files:** none (verification only)

- [ ] **Step 1: Full offline suite** — `python -m pytest -q` → all green.

- [ ] **Step 2: Live E2E** — `python -m aggregator --out out_e2e --db data/e2e.db --today 2026-06-02`

- [ ] **Step 3: Assert wins + no regressions** — from `out_e2e/events.json` confirm:
- CSIS webcast events have `raw["virtual"]`/`attendance_mode` and **no** HQ pin.
- No out-of-bbox pins; events.json count == events.ics VEVENT count; all RSS `bozo=0`.
- Brookings/AC/CNAS still produce events (heuristic fallback unchanged).
- A CSIS event that has both listing + structured times shows an `end` time.

- [ ] **Step 4: Clean scratch** — `rm -rf out_e2e data/e2e.db data/e2e.db-*`

- [ ] **Step 5: Final commit (if verification needed fixes)**
```bash
git add -A && git commit -m "test(accuracy-core): live E2E verification"
```

---

## Self-Review (post round 1)

**Spec coverage:** structured extraction incl `eventAttendanceMode` (T1) ✓; enrich precedence + virtual (T2) ✓; CSIS start+end reconcile (T3) ✓; pre-filter validators, no over-aggressive address nulling (T4) ✓; post-geocode validators with error-vs-miss status, throttle, temp-cache, DC recheck via `is_dc_relevant` (T5) ✓; corrected pipeline order with an explicit replacement block + a real `pipeline.run` test (T6) ✓; live verify (T7) ✓.

**Placeholder scan:** none. The `_reconcile_time` stub (T2) is intentional, replaced in T3. The `aic-washington` non-curated assumption (T5) has an explicit verification command.

**Type consistency:** `extract_structured -> dict` keys consistent T1–T3; `validate_pre_filter`/`validate_post_geocode -> (clean, dropped)` with `query`, `cache_path`, `sleep` params consistent T4–T6; `truth() -> (ok, coords)` used consistently in geo×address and `_address_ok`; `is_dc_relevant`, `score_event(ev, today)`, `_haversine_km`, storage signatures match their real definitions.

**Round-1 fixes applied:** #1 no pre-filter junk-address nulling; #2 non-curated source + verify cmd, non-DC-venue rule deferred (spec updated); #3 error-vs-miss status; #4 temp `cache_path`; #5 CSIS end-time on agreement; #6 explicit pipeline replacement block; #7 real `pipeline.run` integration test; #8 `eventAttendanceMode` + `tz` removed from API; #9 throttle; minor: digit-free overlong-speaker names, replace-through-`return` wording, bash commands.
