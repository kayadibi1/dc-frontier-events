# Provenance Labeling — design (sub-project 3)

**Date:** 2026-06-02
**Status:** Design — revised after Codex review; ready to plan against
**Depends on:** the accuracy core (merged to master).

## Goal

The accuracy core makes values more correct and drops the egregiously wrong ones.
What survives can still be a *reasonable guess* — an event pinned at the org HQ
because no venue was found, a CSIS time assumed Eastern, an auto-extracted speaker
list. Per the brainstorm decision we **keep showing these but label them as derived**,
so a subscriber never sees a guess presented as fact.

Settled requirements: **policy** = label derived values; **fields** = location, time,
speakers; **surfaces** = `.ics`, map, digest + alerts, `events.json`.

Non-goal: changing *which* value is chosen (the accuracy core's job).

## Data model

A per-event provenance map at `ev.raw["provenance"]` = `{field: tag}`, riding the
existing `raw` dict (already JSON-serialized to storage via `Event.to_row` and to
`events.json` via `asdict`). No model/schema change. Only **notable** fields get an
entry; absence = high-confidence feed/scraped value needing no label.

| field | tags (high-confidence … derived) | derived tag(s) to LABEL |
|---|---|---|
| `location` | `structured` · `scraped` · `hq` | **`hq`** ("approx · host venue") |
| `time` | `structured` · `explicit` · `assumed_et` | **`assumed_et`** ("time assumed ET") |
| `speakers` | `structured` · `extracted` | **`extracted`** ("auto-extracted") |

Feed/iCal events (Luma/GWU) keep feed-supplied fields and get no provenance entry.

Helpers in `provenance.py`:
```
def prov_set(ev, field, tag):   ev.raw.setdefault("provenance", {})[field] = tag
def prov_clear(ev, field):      ev.raw.get("provenance", {}).pop(field, None)
def prov_get(ev, field):        return ev.raw.get("provenance", {}).get(field)
```

## Recording points

- **`enrich.py` `one()`** — assign from *separate* sources so the winning branch is
  known (Codex #2). Sketch:
  ```
  structured_addr = st.get("address"); scraped_addr = extract_location(html or "")
  if not ev.address:
      if structured_addr:   ev.address = structured_addr; prov_set(ev,"location","structured")
      elif scraped_addr:    ev.address = scraped_addr;     prov_set(ev,"location","scraped")
      elif not virtual:     ev.address = SOURCE_HQ.get(ev.source,""); prov_set(ev,"location","hq") if ev.address
  structured_spk = [s for s in st.get("speakers",[]) if _looks_like_name(s)]
  if structured_spk:        ev.speakers = structured_spk; prov_set(ev,"speakers","structured")
  else:
      ev.speakers = extract_speakers(html or "")
      if ev.speakers:       prov_set(ev,"speakers","extracted")
  ```
- **`enrich.py` `_reconcile_time()`** (Codex #3) — on an **offset-aware structured
  win** `prov_set(ev,"time","structured")`; on **CSIS naive agreement** leave the
  fetcher's tag; on **conflict downgrade** `prov_clear(ev,"time")` (it's now date-only).
- **`fetchers/csis.py` `parse_csis_listing()`** (Codex confirmed feasible) — using the
  cleaned card text *before* `_parse_when` (do NOT infer from the returned `tz`, which
  is `EDT`/`EST` for both cases): if a time was parsed, `prov_set(ev,"time","explicit")`
  when `re.search(r"E[SD]T", text)` else `"assumed_et"`.

## Validation must clear stale tags (Codex #1)

`validate.py` mutates these same fields, so it clears the matching tag:
- `validate_pre_filter`: timed→date-only downgrade → `prov_clear(ev,"time")`;
  cleaned speaker list empty → `prov_clear(ev,"speakers")`; pure-virtual address
  cleared → `prov_clear(ev,"location")`.
- `validate_post_geocode`: address nulled (unverified) → `prov_clear(ev,"location")`.

## Rendering (`provenance.py`)

Two helpers, and render only where a field is actually shown (Codex #4):
```
MARKER = {("location","hq"): "📍approx"}        # compact, for one-line surfaces
NOTE   = {("location","hq"): "location approximate (host venue)",
          ("time","assumed_et"): "time assumed ET",
          ("speakers","extracted"): "speakers auto-extracted"}
def marker(ev) -> str:   # "" unless a *shown* field is derived; today: location only
def notes(ev) -> list[str]:  # ALL derived labels, for the .ics DESCRIPTION + json
```
Both are **defensive**: `marker`/`notes` for `location` only fire when `ev.address`
is still set; `time` only when `ev.start` is still timed; `speakers` only when
`ev.speakers` is non-empty (belt-and-suspenders over the validation clears).

## Output integration

- **`.ics` (`emit.write_ics`)** — append ` (approx · host venue)` to the `LOCATION`
  value when location is `hq`; add a `Notes: <…>` line built from `notes(ev)` to the
  `DESCRIPTION`. Added via `icalendar` properties (Codex: ICS validity fine; parity is
  UID/count, not byte-equality).
- **map (`emit._li`)** — append ` · 📍approx` to the existing meta line for an
  hq-located event. (Map shows a pin but not the address text, so the location marker
  is the meaningful one; speakers/time are not shown there → no marker.)
- **digest (`digest.py`) + alerts (`alerts.py`)** — append `marker(ev)` to the event
  line where location/venue is shown (`digest._loc`, `alerts._dc_line`). Surfaces that
  show neither location nor speakers get no marker.
- **`events.json`** — `raw["provenance"]` already serialized via `asdict`; add a test
  asserting it appears with the right tags.

## Testing

- `provenance.py` (pure): `prov_set/clear/get`; `marker` returns `📍approx` only for a
  still-addressed hq event, `""` otherwise; `notes` lists all derived labels; defensive
  guards (cleared field → no note).
- `enrich`: location tag `structured`/`scraped`/`hq` per winning branch; speakers
  `structured` vs `extracted`; `_reconcile_time` sets `time=structured` on win, clears
  on conflict.
- `csis`: `assumed_et` (no EDT/EST token) vs `explicit`.
- `validate`: each mutation clears the matching tag (downgrade/empty-speakers/cleared-addr).
- `emit`: hq event `.ics` LOCATION suffix + DESCRIPTION `Notes:` line; structured/feed
  event has neither. `_li` marker present/absent.
- `digest`/`alerts`: marker present for hq event, absent for structured.
- Live: HQ-pinned think-tank events show `📍approx`; structured/feed events clean;
  json↔ics UID/count parity + feed `bozo=0` unchanged.

## Risks

- **Label noise:** `assumed_et` is almost always correct → keep it to a Notes line,
  not a surface marker. The high-value, user-facing marker is `location=hq`.
- **Output churn:** four writers touched; every change is **additive** (append a
  marker/Notes line), never a restructure, so feeds stay valid and parity holds.

## Success criteria

1. `ev.raw["provenance"]` records location/time/speakers rungs at assignment, and
   `validate` clears any tag it invalidates (no stale tags in `events.json`).
2. `location=hq` events show `📍approx` on `.ics`/map/digest/alerts; the `.ics`
   DESCRIPTION lists all derived notes; high-confidence values carry none.
3. `events.json` exposes an accurate provenance map.
4. Full suite green; live json↔ics UID/count parity + feed validity unchanged.
