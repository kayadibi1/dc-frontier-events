# Provenance Labeling — design (sub-project 3)

**Date:** 2026-06-02
**Status:** Design — autonomous (requirements settled in the Tier-3 brainstorm); pending Codex review
**Depends on:** the accuracy core (`structured.py`, `validate.py`, enrich/pipeline changes), already merged to master.

## Goal

The accuracy core makes values *more correct* and drops the egregiously wrong ones.
What survives can still be a *reasonable guess* rather than a scraped fact — an event
pinned at the org HQ because no venue was found, a CSIS time assumed Eastern, an
auto-extracted speaker list. Per the brainstorm decision, we **keep showing these but
label them as derived**, so a subscriber is never shown a guess presented as fact.

Settled requirements (from the brainstorm):
- **Policy:** label derived values (don't hide them).
- **Fields:** location, time, speakers.
- **Surfaces:** `.ics`, map, digest + alerts, `events.json`.

Non-goal: changing *which* value is chosen (that's the accuracy core's job). This
sub-project only **records where each value came from** and **renders a marker** for
the derived rungs.

## Data model

Add a per-event provenance map at `ev.raw["provenance"]` — `{field: tag}`. It rides
the existing `raw` dict (already JSON-serialized to storage and `events.json`), so no
model/schema change. Only **notable** fields get an entry; absence = high-confidence
feed/scraped value needing no label.

Tags:
| field | tags (high-confidence … derived) | derived tag(s) to LABEL |
|---|---|---|
| `location` | `structured` · `scraped` · `hq` | **`hq`** ("approx · host venue") |
| `time` | `structured` · `explicit` · `assumed_et` | **`assumed_et`** ("time assumed ET") |
| `speakers` | `structured` · `extracted` | **`extracted`** ("auto-extracted") |

(Feed/iCal events — Luma/GWU — keep their feed-supplied address/time and get no
provenance entry; they are high-confidence and unlabeled.)

## Recording points (where tags are set)

- **`enrich.py` `one()`** — set `ev.raw["provenance"]["location"]`:
  `"structured"` when `st.get("address")` won, `"scraped"` when `extract_location`
  won, `"hq"` when the `SOURCE_HQ` fallback was used. Set
  `provenance["speakers"]` = `"structured"` when structured performers were used,
  else `"extracted"` when heuristic speakers were found.
- **`enrich.py` `_reconcile_time()`** — set `provenance["time"] = "structured"` when
  an offset-aware structured start wins; leave the listing's own tag otherwise.
- **`fetchers/csis.py` `parse_csis_listing()`** — set `provenance["time"]`:
  `"explicit"` when the card text contains an `EDT`/`EST` token, `"assumed_et"` when
  a time was parsed without one (the `_us_eastern` default fired). No change to
  `_parse_when`'s signature — re-test the card text with `re.search(r"E[SD]T", text)`.

A tiny helper `prov_set(ev, field, tag)` (in `provenance.py`) does
`ev.raw.setdefault("provenance", {})[field] = tag` so callers stay one-liners.

## Rendering (`provenance.py`)

One module owns the vocabulary and the human strings:
```
LABELS = {("location","hq"): "approx · host venue",
          ("time","assumed_et"): "time assumed ET",
          ("speakers","extracted"): "auto-extracted"}
def notes(ev) -> list[str]:   # the derived labels that apply to this event
def location_note(ev) -> str  # "" unless location is derived
def speakers_note(ev) -> str
```
Only the **derived** tags produce a string; high-confidence tags render nothing.

## Output integration

- **`.ics` (`emit.write_ics`)** — when `location_note(ev)`, append ` (approx · host
  venue)` to the `LOCATION` value; append a `Notes: <…>` line to `DESCRIPTION`
  listing all derived labels. Google/Apple Calendar then show the caveat inline.
- **map (`emit._li` / popup)** — add a small ` · approx` marker to the meta line for
  an hq-located event, and an `(auto-extracted)` suffix when speakers are shown.
- **digest (`digest.py`) + alerts (`alerts.py`)** — append the same short markers to
  the event line (e.g. `… · 📍approx`).
- **`events.json`** — `raw["provenance"]` is already serialized via `asdict(ev)`; add
  an explicit assertion/test that it appears.

## Testing

- `provenance.py` (pure): `notes`/`location_note`/`speakers_note` return the right
  strings for each tag; high-confidence tags render `""`.
- `enrich` (extend): location tag is `structured`/`scraped`/`hq` per source; speakers
  tag `structured` vs `extracted`; `_reconcile_time` sets `time=structured` on an
  offset-aware win.
- `csis` (extend): `assumed_et` when no EDT/EST token, `explicit` when present.
- `emit` (extend): an hq event's `.ics` LOCATION carries the suffix and DESCRIPTION a
  `Notes:` line; a structured/feed event carries neither.
- `digest`/`alerts`/map: the marker appears for a derived event, absent otherwise.
- Live: a run shows `📍approx` on the HQ-pinned think-tank events and clean labels on
  the structured/feed ones; json↔ics parity + feed validity hold.

## Risks

- **Label noise.** `assumed_et` is almost always correct (CSIS is always Eastern), so
  its label is low-value; keep it terse. The high-value label is `location=hq`.
- **Output churn.** Touches four writers; keep each change additive (append a marker),
  never restructure existing fields, so feeds stay valid and parity holds.

## Success criteria

1. `ev.raw["provenance"]` records location/time/speakers rungs at their assignment points.
2. Derived values (`hq`, `assumed_et`, `extracted`) carry a visible marker in `.ics`,
   map, digest, alerts; high-confidence values carry none.
3. `events.json` exposes the provenance map.
4. Full suite green; live parity + feed validity unchanged.
