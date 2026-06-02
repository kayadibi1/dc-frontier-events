# Provenance Labeling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** Record where each location/time/speakers value came from in `ev.raw["provenance"]`, and surface a `📍approx` marker (+ `.ics` notes) for the derived rungs, so derived guesses are never shown as fact.

**Architecture:** New `provenance.py` owns the vocabulary, set/clear/get helpers, and the `marker`/`notes` renderers (defensive: only fire when the field is still present). Tags are set at assignment in `enrich.py`/`csis.py`, cleared by `validate.py` when it mutates a field, and rendered into `.ics` (`emit`), the map (`emit._li`), the digest (`digest._loc`, which feeds markdown/web/email), and alerts (`alerts._dc_line`). `events.json` carries `raw["provenance"]` for free.

**Spec:** `docs/superpowers/specs/2026-06-02-provenance-labeling-design.md`. Branch: `sp3-provenance`. Run commands via the Bash tool.

---

### Task 1: `provenance.py` — vocabulary, helpers, renderers

**Files:** Create `aggregator/provenance.py`, `tests/test_provenance.py`

- [ ] **Step 1: Failing tests** — `tests/test_provenance.py`:

```python
from aggregator.models import Event
from aggregator.provenance import marker, notes, prov_clear, prov_get, prov_set


def _ev(**kw):
    kw.setdefault("title", "x"); kw.setdefault("source", "csis"); kw.setdefault("start", "2026-06-10")
    return Event(id="e1", **kw)


def test_set_get_clear():
    ev = _ev()
    prov_set(ev, "location", "hq")
    assert prov_get(ev, "location") == "hq"
    prov_clear(ev, "location")
    assert prov_get(ev, "location") is None


def test_marker_only_for_addressed_hq():
    ev = _ev(address="CNAS, 1701 Pennsylvania Ave NW, Washington, DC 20006")
    prov_set(ev, "location", "hq")
    assert marker(ev) == "📍approx"
    ev.address = ""                       # defensive: cleared address -> no marker
    assert marker(ev) == ""


def test_marker_empty_for_high_confidence():
    ev = _ev(address="123 Real St")
    prov_set(ev, "location", "scraped")
    assert marker(ev) == ""


def test_notes_lists_all_derived_defensively():
    ev = _ev(address="HQ addr", start="2026-06-10T10:00:00", speakers=["A B"])
    prov_set(ev, "location", "hq"); prov_set(ev, "time", "assumed_et"); prov_set(ev, "speakers", "extracted")
    n = notes(ev)
    assert "location approximate (host venue)" in n
    assert "time assumed ET" in n
    assert "speakers auto-extracted" in n
    ev.speakers = []                      # defensive: no speakers -> drop that note
    assert "speakers auto-extracted" not in notes(ev)
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_provenance.py -q` → FAIL (no module)

- [ ] **Step 3: Implement `aggregator/provenance.py`**

```python
"""Field-level provenance: record which rung of the confidence ladder a value came
from (`ev.raw["provenance"][field] = tag`) and render a marker / notes for the
DERIVED rungs, so a guess is never shown as a scraped fact. Renderers are defensive
-- they only fire when the field is still present, so a value that validation later
cleared/downgraded produces no stale label.
"""
from __future__ import annotations

from .models import Event

# Derived tags that earn a user-facing label (high-confidence tags render nothing).
_MARKER = {("location", "hq"): "📍approx"}
_NOTE = {
    ("location", "hq"): "location approximate (host venue)",
    ("time", "assumed_et"): "time assumed ET",
    ("speakers", "extracted"): "speakers auto-extracted",
}


def prov_set(ev: Event, field: str, tag: str) -> None:
    ev.raw.setdefault("provenance", {})[field] = tag


def prov_clear(ev: Event, field: str) -> None:
    ev.raw.get("provenance", {}).pop(field, None)


def prov_get(ev: Event, field: str):
    return ev.raw.get("provenance", {}).get(field)


def _field_present(ev: Event, field: str) -> bool:
    if field == "location":
        return bool(ev.address)
    if field == "time":
        return "T" in (ev.start or "")
    if field == "speakers":
        return bool(ev.speakers)
    return True


def marker(ev: Event) -> str:
    """Compact one-line surface marker (location only today)."""
    for (field, tag), text in _MARKER.items():
        if prov_get(ev, field) == tag and _field_present(ev, field):
            return text
    return ""


def notes(ev: Event) -> list[str]:
    """All derived labels, for the .ics DESCRIPTION + json consumers."""
    out = []
    for (field, tag), text in _NOTE.items():
        if prov_get(ev, field) == tag and _field_present(ev, field):
            out.append(text)
    return out
```

- [ ] **Step 4: Run, verify pass** — `python -m pytest tests/test_provenance.py -q` → PASS (4)

- [ ] **Step 5: Commit**
```bash
git add aggregator/provenance.py tests/test_provenance.py
git commit -m "feat(provenance): provenance map + defensive marker/notes renderers"
```

---

### Task 2: `enrich.py` — record location/speakers/time tags

**Files:** Modify `aggregator/enrich.py`; append `tests/test_enrich.py`

- [ ] **Step 1: Failing tests** (append):

```python
def test_provenance_location_hq_tag():
    from aggregator.provenance import prov_get
    ev = Event(id="csis-p", title="AI", start="2026-06-04", source="csis",
               source_url="https://www.csis.org/events/p")

    async def fake_fetch(url, kind):
        return "<p>nothing structured, no venue</p>"

    asyncio.run(enrich_layer2([ev], {"csis": 2}, fake_fetch))
    assert ev.address == SOURCE_HQ["csis"] and prov_get(ev, "location") == "hq"


def test_provenance_location_structured_tag():
    from aggregator.provenance import prov_get
    ev = Event(id="brk-p", title="AI", start="2026-06-10", source="brookings",
               source_url="https://www.brookings.edu/events/p")

    async def fake_fetch(url, kind):
        return ('<script type="application/ld+json">{"@type":"Event","location":'
                '{"@type":"Place","address":{"@type":"PostalAddress","streetAddress":"1 A St",'
                '"addressLocality":"Washington","addressRegion":"DC","postalCode":"20001"}}}</script>')

    asyncio.run(enrich_layer2([ev], {"brookings": 2}, fake_fetch))
    assert prov_get(ev, "location") == "structured"


def test_provenance_speakers_extracted_tag():
    from aggregator.provenance import prov_get
    ev = Event(id="cset-p", title="AI", start="2026-06-10", source="cset",
               source_url="https://cset.georgetown.edu/event/p")

    async def fake_fetch(url, kind):
        return "<article><p>A discussion featuring Jane Roe and John Doe.</p></article>"

    asyncio.run(enrich_layer2([ev], {"cset": 2}, fake_fetch))
    assert ev.speakers and prov_get(ev, "speakers") == "extracted"
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_enrich.py -k provenance -q` → FAIL

- [ ] **Step 3: Edit `enrich.py`**

Add import (with the other `.` imports):
```python
from .provenance import prov_clear, prov_set
```

In `one()`, replace the speakers block:
```python
        sp = [s for s in st.get("speakers", []) if _looks_like_name(s)]
        ev.speakers = sp or extract_speakers(html or "")
```
with:
```python
        structured_spk = [s for s in st.get("speakers", []) if _looks_like_name(s)]
        if structured_spk:
            ev.speakers = structured_spk
            prov_set(ev, "speakers", "structured")
        else:
            ev.speakers = extract_speakers(html or "")
            if ev.speakers:
                prov_set(ev, "speakers", "extracted")
```

Replace the location block:
```python
        if not ev.address:
            scraped = st.get("address") or extract_location(html or "")
            if scraped:
                ev.address = scraped
            elif not virtual:
                ev.address = SOURCE_HQ.get(ev.source, "")
            added_loc = bool(ev.address)
```
with:
```python
        if not ev.address:
            structured_addr = st.get("address")
            scraped_addr = extract_location(html or "")
            if structured_addr:
                ev.address = structured_addr
                prov_set(ev, "location", "structured")
            elif scraped_addr:
                ev.address = scraped_addr
                prov_set(ev, "location", "scraped")
            elif not virtual:
                ev.address = SOURCE_HQ.get(ev.source, "")
                if ev.address:
                    prov_set(ev, "location", "hq")
            added_loc = bool(ev.address)
```

In `_reconcile_time`, set/clear the time tag. After `if sdt.tzinfo is not None:` (offset-aware win), add `prov_set(ev, "time", "structured")` before `ev.start = s`. In the conflict branch (where `ev.raw["start_conflict"] = True`), add `prov_clear(ev, "time")`.

- [ ] **Step 4: Run, verify pass** — `python -m pytest tests/test_enrich.py -q` → PASS

- [ ] **Step 5: Commit**
```bash
git add aggregator/enrich.py tests/test_enrich.py
git commit -m "feat(enrich): record location/speakers/time provenance tags"
```

---

### Task 3: `fetchers/csis.py` — explicit vs assumed_et time tag

**Files:** Modify `aggregator/fetchers/csis.py`; append `tests/test_csis.py`

- [ ] **Step 1: Failing tests** (append to `tests/test_csis.py`):

```python
def test_provenance_time_assumed_vs_explicit():
    from aggregator.provenance import prov_get
    html = """<div class="grid">
      <article class="ts-card-event-sm"><a href="/events/explicit-t"></a>
        <h3>Explicit AI</h3><span>June 3, 2026 - 3:30 - 4:45 pm EDT</span>
        <a href="/programs/x">X</a></article>
      <article class="ts-card-event-sm"><a href="/events/assumed-t"></a>
        <h3>Assumed AI</h3><span>June 4, 2026 - 11:00 am ET</span>
        <a href="/programs/y">Y</a></article>
    </div>"""
    by_id = {e.id: e for e in parse_csis_listing(SRC, html)}
    assert prov_get(by_id["csis-explicit-t"], "time") == "explicit"
    assert prov_get(by_id["csis-assumed-t"], "time") == "assumed_et"
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_csis.py -k provenance -q` → FAIL

- [ ] **Step 3: Edit `csis.py`**

Add import:
```python
from ..provenance import prov_set
```
In `parse_csis_listing`, where the `Event(...)` is built from `start, tz = _parse_when(text)` (the `text` is the cleaned card text already passed to `_parse_when`), after constructing the event and before/after appending, tag the time. Concretely, right after `start, tz = _parse_when(text)` and the `if not start: continue`, compute:
```python
        if "T" in start:
            ev_time_tag = "explicit" if re.search(r"E[SD]T", text) else "assumed_et"
        else:
            ev_time_tag = None
```
and after the event is appended (you have the `Event` object — capture it as `ev = Event(...)` then `events.append(ev)`), do:
```python
        if ev_time_tag:
            prov_set(ev, "time", ev_time_tag)
```
(`text` here is the `_clean(card.text())` value already computed for `_parse_when`; `re` is already imported in csis.py.)

- [ ] **Step 4: Run, verify pass** — `python -m pytest tests/test_csis.py -q` → PASS

- [ ] **Step 5: Commit**
```bash
git add aggregator/fetchers/csis.py tests/test_csis.py
git commit -m "feat(csis): tag time provenance explicit vs assumed_et"
```

---

### Task 4: `validate.py` — clear stale tags on mutation

**Files:** Modify `aggregator/validate.py`; append `tests/test_validate.py`

- [ ] **Step 1: Failing tests** (append):

```python
from aggregator.provenance import prov_get, prov_set


def test_validate_clears_time_tag_on_downgrade():
    ev = _ev(start="2026-06-10T11:00:00", tz=None)
    prov_set(ev, "time", "assumed_et")
    validate_pre_filter([ev], T)
    assert prov_get(ev, "time") is None       # downgraded to date-only


def test_validate_clears_location_tag_on_virtual_clear():
    ev = _ev(address="CSIS HQ", raw={"virtual": True, "provenance": {"location": "hq"}})
    validate_pre_filter([ev], T)
    assert prov_get(ev, "location") is None


def test_validate_clears_speakers_tag_when_emptied():
    ev = _ev(speakers=["EDT Brought"])            # junk -> cleaned to []
    prov_set(ev, "speakers", "extracted")
    validate_pre_filter([ev], T)
    assert ev.speakers == [] and prov_get(ev, "speakers") is None
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_validate.py -k "clears" -q` → FAIL

- [ ] **Step 3: Edit `validate.py`**

Add import:
```python
from .provenance import prov_clear
```
In `validate_pre_filter`: in the timed-no-tz downgrade branch add `prov_clear(ev, "time")`; in the speaker-cleanup branch, after setting `ev.speakers = cleaned`, add `if not ev.speakers: prov_clear(ev, "speakers")`; in the pure-virtual address-clear branch add `prov_clear(ev, "location")`.
In `validate_post_geocode`: in the `_address_ok` failure branch (where `ev.address = ""`) add `prov_clear(ev, "location")`.

- [ ] **Step 4: Run, verify pass** — `python -m pytest tests/test_validate.py -q` → PASS

- [ ] **Step 5: Commit**
```bash
git add aggregator/validate.py tests/test_validate.py
git commit -m "feat(validate): clear stale provenance tags when fields are mutated"
```

---

### Task 5: `emit.py` — `.ics` LOCATION suffix + DESCRIPTION notes + map marker

**Files:** Modify `aggregator/emit.py`; append `tests/test_emit.py`

- [ ] **Step 1: Failing tests** (append to `tests/test_emit.py`):

```python
def test_ics_location_suffix_and_notes_for_hq():
    from icalendar import Calendar
    from aggregator.provenance import prov_set
    ev = Event(id="h", title="Panel", start="2026-06-10", source="csis",
               address="CSIS, 1616 Rhode Island Ave NW, Washington, DC 20036")
    prov_set(ev, "location", "hq")
    write_ics([ev], "out_test/p.ics", "2026-06-01")
    cal = Calendar.from_ical(open("out_test/p.ics", "rb").read())
    ve = next(iter(cal.walk("VEVENT")))
    assert "approx" in str(ve.get("location"))
    assert "host venue" in str(ve.get("description"))


def test_ics_no_suffix_for_scraped():
    from icalendar import Calendar
    from aggregator.provenance import prov_set
    ev = Event(id="s", title="Panel", start="2026-06-10", source="brookings",
               address="Saul Auditorium, 1775 Massachusetts Ave NW, Washington, DC 20036")
    prov_set(ev, "location", "scraped")
    write_ics([ev], "out_test/s.ics", "2026-06-01")
    cal = Calendar.from_ical(open("out_test/s.ics", "rb").read())
    ve = next(iter(cal.walk("VEVENT")))
    assert "approx" not in str(ve.get("location"))
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_emit.py -k "suffix or notes" -q` → FAIL

- [ ] **Step 3: Edit `emit.py`**

Add import:
```python
from .provenance import marker, notes
```
In `write_ics`, where `if ev.address: ie.add("location", ev.address)` — change to append the suffix when the location is approximate:
```python
        if ev.address:
            loc = ev.address + (" (approx · host venue)" if marker(ev) else "")
            ie.add("location", loc)
```
Where `DESCRIPTION` is built (`desc = ev.description` … then `ie.add("description", desc)`), append a notes line before adding:
```python
        prov_notes = notes(ev)
        if prov_notes:
            desc = f"{desc}\n\nNotes: {'; '.join(prov_notes)}".strip()
        ie.add("description", desc)
```
In `_li` (map), append the marker to the `meta` line:
```python
    meta = f"{date} · {_h(src)} · {_h(topics) or '—'}"
    if marker(ev):
        meta += f" · {marker(ev)}"
    if score is not None:
        meta += f" · ●{score}"
```

- [ ] **Step 4: Run, verify pass + full emit** — `python -m pytest tests/test_emit.py -q` → PASS

- [ ] **Step 5: Commit**
```bash
git add aggregator/emit.py tests/test_emit.py
git commit -m "feat(emit): .ics approx-location suffix + Notes line; map approx marker"
```

---

### Task 6: `digest.py` + `alerts.py` — surface markers

**Files:** Modify `aggregator/digest.py`, `aggregator/alerts.py`; append `tests/test_digest.py`, `tests/test_alerts.py`

- [ ] **Step 1: Failing tests**

Append to `tests/test_digest.py`:
```python
def test_digest_loc_shows_approx_marker():
    from aggregator.digest import _loc
    from aggregator.provenance import prov_set
    ev = Event(id="d", title="x", start="2026-06-10", source="csis", address="CSIS HQ addr")
    prov_set(ev, "location", "hq")
    assert "📍approx" in _loc(ev)
    ev2 = Event(id="d2", title="x", start="2026-06-10", source="brookings", address="Real Venue")
    prov_set(ev2, "location", "scraped")
    assert "📍approx" not in _loc(ev2)
```
Append to `tests/test_alerts.py`:
```python
def test_alerts_dc_line_shows_approx_marker():
    from aggregator.alerts import _dc_line
    from aggregator.provenance import prov_set
    ev = Event(id="a", title="x", start="2026-06-10", source="csis",
               venue_name="CSIS", address="CSIS HQ", lat=38.9, lng=-77.04, is_big_name=True)
    prov_set(ev, "location", "hq")
    assert "📍approx" in _dc_line(ev)
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_digest.py tests/test_alerts.py -k approx -q` → FAIL

- [ ] **Step 3: Edits**

`digest.py` — add `from .provenance import marker`, and in `_loc`, append the marker:
```python
def _loc(ev: Event) -> str:
    base = ev.address if ev.address else ("virtual" if ev.raw.get("virtual") else "TBD")
    m = marker(ev)
    return f"{base} {m}" if (m and ev.address) else base
```
`alerts.py` — add `from .provenance import marker`, and in `_dc_line`, append the marker to the returned line, e.g. change the `venue` piece:
```python
    venue = f" @ {e.venue_name}" if e.venue_name else ""
    approx = f" {marker(e)}" if marker(e) else ""
    return f"- **{(e.start or '')[:10]}** · {e.title}{who_s} · {src}{venue}{approx}{link}"
```

- [ ] **Step 4: Run, verify pass + full suite** — `python -m pytest tests/test_digest.py tests/test_alerts.py -q` → PASS; then `python -m pytest -q` → all green.

- [ ] **Step 5: Commit**
```bash
git add aggregator/digest.py aggregator/alerts.py tests/test_digest.py tests/test_alerts.py
git commit -m "feat(digest,alerts): show approx-location marker"
```

---

### Task 7: Verify + merge

- [ ] **Step 1: Full suite** — `python -m pytest -q` → all green.
- [ ] **Step 2: Live E2E** — `python -m aggregator --out out_e2e --db data/e2e.db --today 2026-06-02`
- [ ] **Step 3: Assert** — from `out_e2e/events.json`: HQ-pinned think-tank events carry `raw["provenance"]["location"]=="hq"`; CSIS events show a `time` tag; `events.ics` LOCATION for an hq event ends with `(approx · host venue)`; json↔ics UID/count parity; feeds `bozo=0`.
- [ ] **Step 4: Clean** — `rm -rf out_e2e data/e2e.db data/e2e.db-*`
- [ ] **Step 5: Merge** — `git switch master && git merge --ff-only sp3-provenance && git push origin master`

---

## Self-Review

**Spec coverage:** provenance map + helpers (T1) ✓; recording location/speakers/time, branch-split (T2) ✓; csis explicit/assumed (T3) ✓; validation clears stale tags (T4) ✓; .ics suffix+notes + map marker (T5) ✓; digest+alerts markers (T6) ✓; json carries raw (free) ✓; verify+merge (T7) ✓.

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `prov_set/clear/get(ev, field[, tag])`, `marker(ev)->str`, `notes(ev)->list[str]` used consistently across T1–T6; `_loc`/`_dc_line`/`_li`/`write_ics` edits match the real current signatures.
