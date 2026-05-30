# ICS Enrichment (COLOR + VALARM) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the emitted calendar more useful in clients: colour each event by category (big-name / layer) via the RFC 7986 `COLOR` property, and attach a `VALARM` reminder (1 day before) to upcoming events.

**Architecture:** Extend `emit.write_ics` to add a per-event `COLOR` and, for events at/after `today`, a `DISPLAY` `VALARM`. `write_ics` gains an optional `today_iso` param (None → no alarms, preserving existing call sites/tests). Pipeline passes `today`.

**Tech Stack:** Python 3.11+, icalendar (`Alarm`), pytest.

---

### Task 1: Per-event COLOR

**Files:**
- Modify: `aggregator/emit.py` (`write_ics`)
- Test: `tests/test_emit.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_emit.py`)

```python
def test_ics_per_event_color(tmp_path):
    evs = [
        Event(id="big", title="Fireside", start="2026-06-10", source="csis",
              is_big_name=True, topics=["ai"]),
        Event(id="comm", title="Meetup", start="2026-06-10", source="DC2", topics=["ai"]),
    ]
    p = tmp_path / "c.ics"
    write_ics(evs, str(p))
    raw = p.read_text(encoding="utf-8")
    assert "COLOR:red" in raw          # big-name -> red
    cal = Calendar.from_ical(p.read_bytes())
    colors = {str(v.get("uid")): str(v.get("color")) for v in cal.walk("VEVENT")}
    assert colors["big"] == "red"
    assert colors["comm"] == "blue"    # Layer-1 community -> blue
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_emit.py::test_ics_per_event_color -q`
Expected: FAIL (no COLOR property emitted yet)

- [ ] **Step 3: Add COLOR in `write_ics`**

In `aggregator/emit.py`, inside the `for ev in events:` loop of `write_ics`, after the
`categories` block and before `ie.add("description", desc)`, add:

```python
        color = ("red" if ev.is_big_name
                 else {2: "purple", 3: "green"}.get(_LAYER.get(ev.source, 1), "blue"))
        ie.add("color", color)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_emit.py -q`
Expected: PASS (all emit tests)

- [ ] **Step 5: Commit**

```bash
git add aggregator/emit.py tests/test_emit.py
git commit -m "emit: per-event COLOR (RFC 7986) by big-name/layer"
```

---

### Task 2: VALARM reminders for upcoming events

**Files:**
- Modify: `aggregator/emit.py` (import `Alarm`; `write_ics` signature + alarm block)
- Test: `tests/test_emit.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_emit.py`)

```python
def test_ics_valarm_only_for_upcoming(tmp_path):
    evs = [
        Event(id="future", title="Upcoming AI", start="2026-12-01", source="DC2", topics=["ai"]),
        Event(id="past", title="Old AI", start="2024-01-01", source="DC2", topics=["ai"]),
    ]
    p = tmp_path / "a.ics"
    write_ics(evs, str(p), "2026-05-29")
    cal = Calendar.from_ical(p.read_bytes())
    alarms = {str(v.get("uid")): len(list(v.walk("VALARM"))) for v in cal.walk("VEVENT")}
    assert alarms["future"] == 1
    assert alarms["past"] == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_emit.py::test_ics_valarm_only_for_upcoming -q`
Expected: FAIL (`write_ics() takes 2 positional arguments but 3 were given`)

- [ ] **Step 3: Update `write_ics`**

At the top of `aggregator/emit.py`, extend the icalendar import:
```python
from icalendar import Alarm, Calendar
from icalendar import Event as IcsEvent
```
Also ensure `timedelta` is imported: change the datetime import to
`from datetime import date, datetime, timedelta, timezone`.

Change the signature:
```python
def write_ics(events: list[Event], path: str, today_iso: str | None = None) -> int:
```

Inside the loop, after the `ie.add("color", color)` line, add:
```python
        if today_iso and (ev.start or "")[:10] >= today_iso:
            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", ev.title)
            alarm.add("trigger", timedelta(days=-1))   # 1 day before
            ie.add_component(alarm)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_emit.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aggregator/emit.py tests/test_emit.py
git commit -m "emit: VALARM (1-day) reminders on upcoming events"
```

---

### Task 3: Pass `today` from the pipeline

**Files:**
- Modify: `aggregator/pipeline.py`

- [ ] **Step 1: Pass `today` to the main + upcoming + archive ICS writers**

In `run(...)`, update the `write_ics` calls to pass `today`:
```python
    ics_n = write_ics(emitted, f"{out_dir}/events.ics", today)
    ...
    up_n = write_ics(upcoming, f"{out_dir}/events-upcoming.ics", today)
    ...
    archive_n = write_ics(sorted(roundtrip, key=lambda e: e.start or ""),
                          f"{out_dir}/events-archive.ics", today)
```
(Leave `write_ics(big, ...)` for `events-big-names.ics` as-is or add `today` too — your
choice; big-names benefit from reminders, so pass `today` there as well.)

- [ ] **Step 2: Run full suite + live**

Run: `python -m pytest tests/ -q` (Expected: PASS)
Run: `python -m aggregator` then:
```bash
grep -c "BEGIN:VALARM" out/events.ics
grep -c "^COLOR:" out/events.ics
```
Expected: VALARM count == number of upcoming events; COLOR count == VEVENT count.

- [ ] **Step 3: Commit + docs**

```bash
git add aggregator/pipeline.py PROGRESS.md BACKLOG.md
git commit -m "emit: pass today for VALARMs; record ICS enrichment results"
```

---

## Notes
- **COLOR** is RFC 7986 (a CSS3 colour name); supported by modern calendar clients and
  ignored gracefully by older ones — safe to always emit.
- **VALARM** uses a relative `TRIGGER` (`-P1D`), so it fires 1 day before regardless of tz.
  Only upcoming events get one (no point alarming past events).
- **Backward compatible:** `today_iso` defaults to `None`, so existing `write_ics(events, path)`
  calls and tests keep working (no alarms emitted).
