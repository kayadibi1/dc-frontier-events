# Accuracy Core — authoritative extraction + validation gate

**Date:** 2026-06-02
**Status:** Design — revised after two Codex (gpt-5.5, xhigh) reviews; ready to plan against
**Scope:** Sub-project 1 of a "robust accuracy" effort. Covers the *accuracy core*
only: (1) authoritative structured-data extraction and (2) a two-phase validation /
cross-check gate. Two follow-on sub-projects are **out of scope** (see Non-goals):
provenance labeling in outputs, and a periodic live ground-truth audit.

## Problem & goal

A live audit found field-level inaccuracies the source-level "quarantine, never
fake" policy didn't catch: a wrong hardcoded HQ address (B1), a junk mid-Pacific
GEO on a virtual event (B2), virtual events pinned at the org HQ (B3), polluted
speaker lists (B4), a dropped timezone (B5). Those are fixed (four were logic
fixes that protect future runs); the open question is keeping **future** runs
accurate against sites that change under us.

**Honest ceiling.** No system can *guarantee* accuracy against sites we don't
control. The achievable goal is a **confidence ladder**: (1) source from
authoritative structured data when published; (2) cross-check / validate and drop
a field rather than emit it wrong; (3) graceful fallback to heuristics when
structured data is absent; (4, deferred) label surviving guesses; (5, deferred)
verify against live ground truth on a schedule. This spec builds rungs 1–3.

## Evidence: structured-data availability (probed 2026-06-02)

| Source | `Event` JSON-LD? | Notes |
|---|---|---|
| CSIS | **yes** | `VirtualLocation` (authoritative virtual flag) + exact start/end (naive **UTC**) |
| Brookings | no | only `WebPage`/`NewsArticle` → heuristics |
| Atlantic Council | no | only `WebPage`/`Organization` → heuristics |
| CNAS | no | `WebSite`/`LocalBusiness` → heuristics |
| Luma (Layer 1) | yes, but **N/A** | Luma comes via **iCal**, already authoritative; we do **not** fetch Luma detail pages |

**Implication:** the only Layer-2 source that materially benefits today is **CSIS**
(authoritative virtual flag + exact times); the other three think tanks fall
through to heuristics. Luma stays iCal-authoritative. This spec does not fabricate
data the sites don't publish, and does not add Layer-1 detail-page fetching.

## Architecture

Two new pure modules + edits to `enrich.py` and `pipeline.py`.

- **New `aggregator/structured.py`** — `extract_structured(html) -> dict`. Pure
  reader of authoritative markup (JSON-LD `Event` → microdata). Returns only fields
  it confidently finds.
- **New `aggregator/validate.py`** — **two** pure entry points:
  - `validate_pre_filter(events, today_iso) -> (clean, dropped)` — offline field
    cleanups that the filter consumes. Runs **before** dedupe/filter.
  - `validate_post_geocode(events, today_iso, query=None) -> (clean, dropped)` —
    coordinate-dependent checks. Runs **after** geocode. `query=None` skips the one
    networked check (under `--no-enrich`); deterministic in tests via injected
    `query` + the on-disk geocode cache.
  - The existing **`scrub_far_geo` stays as a pre-geocode step** (between filter and
    geocode), **not** absorbed: it nulls out-of-DC feed GEO so `geocode_events` can
    re-pin from a real DC address (this is the B2 fix; moving it after geocode would
    regress it). `validate_post_geocode` re-checks bbox only as a final safety.
- **Edit `enrich.py`** — call `extract_structured` first in `enrich_layer2`; apply
  field precedence + CSIS time reconciliation; record virtual state in `raw`.
- **Edit `pipeline.py`** — insert both validation phases, keep `scrub_far_geo`
  before geocode, reorder so scoring happens after final coordinates, store the
  validated active set, log per-validator counts.

**Why two phases:** several validators mutate fields `apply_filters` reads (date,
location/virtual, speakers feeding `is_big_name`); those must run **before** the
filter. The geo checks need coordinates, which only exist **after** geocode. A
single post-geocode gate would either let an event survive on a basis validation
later invalidates, or require re-running `apply_filters`, which isn't safely
idempotent. Plus a third touchpoint: the **bbox scrub before geocode** (B2).

### Corrected pipeline order

```
fetch → raw_events
enrich_layer2(raw_events)                 # structured extraction + CSIS time reconcile (if enrich)
validate_pre_filter(raw_events, today)    # date / timed-naive / speakers / virtual / junk-addr
dedupe → apply_filters → kept
prior_ids = store.existing_ids()          # before any upsert (includes archived rows)
scrub_far_geo(kept)                       # null out-of-DC feed GEO BEFORE geocode (B2: lets a DC address re-pin)
geocode_events(kept)                      # (if enrich) fills coords on think-tank events
validate_post_geocode(kept, today, query) # geo-vs-address + final bbox safety + DC recheck
  → clean                                 # excluded events removed here
store.upsert_many(clean)                  # store the VALIDATED active set (no runtime score yet)
mark_archived({clean ids}); prune(cutoff) # demote-not-delete; previously-active failures archive
roundtrip = store.all_events()
for e in clean: e.raw["score"] = score_event(e, today)   # ephemeral; set AFTER store
derive big / upcoming / top / new(vs prior_ids) / big_in_dc  from clean
emit main feeds / json / map / digest / alerts from clean; archive from roundtrip
```

Two ordering rules this enforces, both fixing latent issues:
1. **Scoring after final coordinates.** Today scoring runs *before* geocode, so
   geocoded think-tank events get no `score_event` DC-proximity bonus. Scoring after
   geocode+validate fixes it.
2. **Store before scoring.** `raw["score"]` is `today`-dependent/ephemeral; current
   code avoids persisting it by storing before scoring. Preserved.

## Component 1 — `structured.py`

`extract_structured(html) -> dict` with any of: `start`, `end`, `tz`,
`venue_name`, `address`, `virtual` (bool), `attendance_mode`, `speakers`. Present
only when confidently found.

**JSON-LD (primary).** Walk every `<script type="application/ld+json">`; handle
single object / array / `@graph`; pick the node whose `@type` is/includes `Event`.
- `location`: a `Place` → `venue_name` + formatted `PostalAddress`. A
  `VirtualLocation` (or `eventAttendanceMode` containing `Online`) → `virtual=True`.
  **Hybrid:** `location` a list with *both* a `Place` and a `VirtualLocation` →
  keep the physical address, set `attendance_mode="mixed"` (not pure-virtual).
- `performer` (Person/list) → `speakers` (run through `_looks_like_name`).
- `startDate`/`endDate` → `start`/`end`; `tz` set **only when offset-aware**.

**Microdata** (`schema.org/Event` itemprops) fills genuinely missing fields.
**JSON-LD `Event` is the only source permitted to set `start`/`end`/`address`** —
generic page metadata (`og:*`, `article:published_time`, `datePublished`,
`Organization` address) is **never** used for event time or venue (OG may at most
fill a missing title/description). Malformed JSON-LD never crashes (skip the
block); a page with no `Event` returns `{}`.

## Component 2 — time reconciliation (in `enrich.py`)

"Authoritative" for time means **offset-aware**, not "from JSON-LD".
- Structured time **offset-aware** → use it.
- Structured time **naive** + listing already offset-aware (CSIS) → keep the
  listing's, and **cross-check**: interpret the naive structured value **as UTC —
  CSIS-scoped only** (other sites may emit naive-local) — and confirm it equals the
  listing instant. Record the candidate + agreement/conflict in `raw`
  (`raw["start_structured"]`, `raw["start_conflict"]`). On **conflict**, downgrade
  `start`, `end`, and `tz` together to date-only.
- Only naive structured time, nothing to cross-check → keep date, drop the time.

`virtual` from `VirtualLocation` is **authoritative** for CSIS and is written to
`raw["virtual"]` / `raw["attendance_mode"]` (no new `Event` field — `Event` has no
`is_virtual`, and digest/filter already use `raw`/text). The B3 regex remains the
fallback for the JSON-LD-less sources. A virtual (non-hybrid) event skips the
HQ-address fallback (existing B3 behavior).

## Component 3 — validation (two phases, `validate.py`)

Each validator prefers omission/downgrade over a wrong value and appends
`(event_id, field, reason)` to `dropped`. `today_iso` is **injected** (never wall-clock).

**`validate_pre_filter(events, today_iso)` — offline, before dedupe/filter:**

| Field | Check | On failure |
|---|---|---|
| date | parseable and the start **date** is within `[today−3y, today+3y]` (a real date comparison; catches a misparse; deliberately wide, **not** a pruning tool) | exclude the event |
| time/tz | a timed `start` has `datetime.fromisoformat(start).tzinfo` | downgrade to date-only (clear time on `start`/`end`, clear `tz`) |
| speakers | each passes `_looks_like_name`; cleaned list ≤ 12 | drop names failing `_looks_like_name`; if still > 12, drop the **whole** list (over-long ⇒ nav pollution; capping keeps junk) — before the filter computes `is_big_name` |
| virtual | normalize `raw["virtual"]`/`attendance_mode`; a pure-virtual event carries no physical-venue fallback | clear the spurious address |
| address (junk) | not obvious nav junk (length / token sanity) | null address |

**`validate_post_geocode(events, today_iso, query=None)` — after geocode:**

| Field | Check | On failure | Cost |
|---|---|---|---|
| geo (final safety) | within `DC_BBOX` — a re-check; the primary bbox scrub is `scrub_far_geo` running **before** geocode (junk feed GEO nulled first, so a DC address can re-pin) | null lat/lng | free |
| geo × address | **contradiction check** — geocode the address (cached) and prune the pin only on *positive contradictory evidence*: it resolves > threshold from the stored coord. Tighter threshold for exact street addresses (~2 km) than venue-name-only (~10 km). A geocoder miss/exception is **not** evidence → never prune on it. | null lat/lng | 1 cached geocode |
| address | has a ZIP, OR matches a `SOURCE_HQ`, OR geocoded to a pin; **never null a ZIP-less address when geocoding is unavailable** (`query is None`) | null address | free |
| DC recheck | after the mutations, re-assert DC relevance by reusing **`filter.is_dc_relevant`** (pure, idempotent — unlike `apply_filters`). When an address was nulled, **clear the matching `raw["location"]` text** for the recheck so stale "Washington DC" text can't keep a now-locationless event alive. | exclude the event | free |

*(Deferred: "an explicit non-DC physical venue from a curated source blocks the HQ fallback" — no observed case; the geo-bbox + geo×address checks already catch gross errors. Revisit if it ever occurs.)*

Thresholds (`±3y`, `≤12` speakers, `~2 km` / `~10 km`) are tunable module constants.

**Limits:** geo × address catches *gross* feed inconsistencies (pin in a different
city than the address), **not** B1-style wrong HQs — clustered DC HQs make distance
a contradiction signal, not a truth oracle. **B1-class errors stay guarded by the
direct `SOURCE_HQ` Tier-0 test, not this validator.**

## Pipeline integration & storage notes

- `validate_pre_filter` runs right after `enrich_layer2`. `scrub_far_geo` stays
  before `geocode_events`. `validate_post_geocode` replaces the *post*-geocode work.
- Store the **validated** `clean` set; `mark_archived({clean ids})` demotes any
  previously-active event that now fails (**demote, not delete** — deletion stays
  the existing `prune` policy).
- `store.existing_ids()` includes archived rows (unchanged), so a re-surfacing event
  won't false-alert as "new" — preserved.
- **Archive is historical.** `events-archive.ics` is built from `store.all_events()`;
  an event active before but now failing post-geocode validation is demoted and its
  *prior* snapshot may remain in the archive feed — archive is a durable record, not
  a live view. Pre-filter exclusions never entered the store, so appear nowhere.
- The weekly emailer reads the store's active rows — now only validated rows, an
  improvement, no break expected.
- Run summary gains counts: `pre-excluded, post-excluded, geo-nulled, addr-nulled,
  time-downgraded, speakers-cleaned`.

## Testing

Offline + deterministic except a final live run (real fixtures + injected geocoder).

**`structured.py` (pure).** Primary fixtures are **saved real JSON-LD** from a live
CSIS page (per the BACKLOG lesson) + synthetic cases:
- real CSIS block → `virtual=True`, naive start surfaced (tz absent)
- offset-aware synthetic block → tz kept
- **hybrid** (`[Place, VirtualLocation]`) → physical address kept, `attendance_mode="mixed"`
- `@graph`/array/single-object; malformed JSON-LD → `{}`; non-Event page → `{}`
- **OG/`datePublished` must NOT set event time/address** (negative test)

**`enrich.py` (extend `test_enrich.py`).**
- structured present → wins over heuristic (location, virtual)
- structured absent → existing heuristic path unchanged (regression guard)
- CSIS naive-UTC: agreement keeps listing time; **conflict downgrades start+end+tz**;
  candidate/conflict recorded in `raw`

**`validate.py` (pure, injected geocoder).**
- pre: date implausible/unparseable → excluded; timed-no-tzinfo → downgraded;
  over-long speaker list → **dropped wholesale**; spurious virtual address → cleared
- post: geo×address far → pin nulled, near → kept, **geocoder exception → not
  pruned**; ZIP-less address with `query=None` → kept; DC recheck excludes a
  now-locationless non-DC event and masks stale `raw["location"]`

**Pipeline + live (integration — the reviews' emphasis).**
- `scrub_far_geo` runs before geocode: a junk feed GEO is nulled, then the event
  re-pins from its DC address (B2 re-pin preserved)
- pre-filter-excluded events never enter the store; post-geocode failures are absent
  from active store, main feeds, "new", and email (archive **may** retain a prior
  snapshot — asserted as documented behavior)
- `--no-enrich` still runs offline validators; the networked check is skipped
- score is recomputed after final coords; `raw["score"]` is **not** persisted
- hybrid JSON-LD keeps physical location end-to-end
- full live run + gate-check: CSIS carries an authoritative virtual flag and
  cross-confirmed time; json↔ics parity and feed validity hold; Brookings/AC/CNAS
  heuristic fallback unchanged

## Non-goals (deferred sub-projects)

- Provenance dict + output labeling (sub-project 3); the `dropped` log is its seed.
- Periodic live ground-truth audit (`--audit`, sub-project 4).
- Big-name flag provenance (mention vs participant).

## Risks & limits

- **No silver bullet:** only CSIS gains authoritative data; the rest rest on
  heuristics + validation + honest omission.
- **geo × address is a contradiction check, not an oracle** — won't catch subtle
  wrong-HQ pins (Tier-0 test's job); never prunes on a transient geocoder failure.
- **New Nominatim calls** ride the existing on-disk cache (amortized, ≤1/s, best-effort).
- **`apply_filters` non-idempotency** drives the pre/post split — to be confirmed
  during implementation (it sets `is_big_name`/`big:*` tags).
- Structured data can itself be stale/wrong (rare); the cross-check guards gross
  cases, the deferred live audit is the longer-term net.

## Success criteria

1. CSIS events derive their virtual flag and confirm their start time from JSON-LD
   (not the regex / a naive parse), verified live; a synthetic conflict downgrades
   to date-only.
2. Both validation phases enforce every rule above. Pre-filter exclusions never
   enter the store; post-geocode failures stay out of the active store, main feeds,
   email, and "new" alerts. (The historical archive feed may retain a prior snapshot
   of an event that later fails — by design.)
3. `scrub_far_geo` still runs before geocode (B2 re-pin preserved); scoring uses
   final coordinates; `raw["score"]` is not persisted.
4. All new logic covered by offline tests (real fixtures + injected geocoder) plus
   the integration tests above; full suite green; Brookings/AC/CNAS unchanged.
