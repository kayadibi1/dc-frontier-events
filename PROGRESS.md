# PROGRESS — dc-frontier-events

## Status: Phase 1 spine COMPLETE and verified end-to-end on live data.

## Iteration 1 (2026-05-29) — Prove the spine
Built the full pipeline `fetch → normalize → dedupe → filter → store → emit` as the
`aggregator/` package, wired to **real Luma iCal subscription feeds** (Layer 1), with
SQLite storage, dedupe, a DC + topic + big-name filter, and valid `.ics` + RSS output.

### What was built
- `aggregator/config.py` — sources (5 Luma calendars), topic patterns, big-name watchlist, DC bbox + text matchers.
- `aggregator/fetchers.py` — async `httpx` fetch of Luma `ics/get` endpoints; per-source `FetchResult` (status/error) so empty/failed sources are quarantined, never faked.
- `aggregator/normalize.py` — `icalendar` VEVENT → `Event` (id from UID, GEO lat/lng, source_url + address from DESCRIPTION, topic tagging).
- `aggregator/dedupe.py` — exact-UID collapse (cross-listed Luma events) + fuzzy title-within-day (`difflib`) for cross-platform dupes.
- `aggregator/filter.py` — keep iff `(DC-metro OR virtual-from-DC-curated) AND (on-topic OR big-name)`; **GEO authoritative for in-person events**; sets `is_big_name`.
- `aggregator/storage.py` — SQLite store w/ idempotent INSERT-OR-REPLACE upsert; `DATABASE_URL`→logs fallback to SQLite (never blocked on infra).
- `aggregator/emit.py` — valid `events.ics` (icalendar) + `feed.xml` (RSS 2.0) + big-names-only variants.
- `aggregator/pipeline.py` — orchestration + concrete count logging; emits from the fresh `kept` set, store is the durable archive.
- `tests/` — 19 unit tests (normalize, dedupe, filter, emit) — all pass.

### Verification numbers (live run, 2026-05-29)
- **Unit tests: 19 passed.**
- **Sources: 3/5 live** across **Layer 1** — DC2=72, dctech=24, aic-washington=455 (551 raw events).
  - Quarantined (logged, not faked): `DCtechevents` (HTTP 200, 0 events), `ai` (HTTP 404).
- **Dedupe: 551 → 454** (97 cross-listed dupes removed).
- **Filter: 454 → 55 kept** (dropped 348 on location, 51 on topic).
- **Big-name: 0.** Honest + expected: the 3 big-name mentions in live data (Microsoft→Chicago, OpenAI→non-DC hackathon, Anthropic→"Let's Master Claude" non-DC) are all **outside DC**. This confirms GOAL's thesis — DC big-names live in **Layer 2** (CSET/CSIS), not the builder calendars.
- **Emit: events.ics = 55 VEVENTs** (parses with `icalendar`, 0 malformed); **feed.xml = 55 entries** (`feedparser` bozo=False). 4 feeds written.
- **Precision audit: 0** in-person events with non-DC geo in the kept set.
- **Idempotent:** re-run holds stored=55, emitted=55.

### Bugs found & fixed by verification this iteration
1. `aic-washington` is a **global** calendar (only ~11/455 events in DC) — was wrongly `dc_curated`; reclassified. Its no-geo global events (e.g. "SF GAI Meetup") were leaking in.
2. **GEO made authoritative for in-person events** — 3 Hampton Roads, VA events (~200mi away, "AI Collective HR") leaked via ", VA" text; now dropped. A virtual DC2 event with a junk Pacific-Ocean geo is still correctly kept.

## SINGLE BEST NEXT STEP
**Add the Layer-2 CSET (Georgetown) events scraper** (`async httpx` + `selectolax`).
Rationale: it satisfies the still-unmet project gate "≥3 sources across **≥2 layers**" AND
surfaces the first *real DC big-name* events (the core differentiator). See BACKLOG.md #1.

## Known simplifications (tracked in BACKLOG.md)
- Postgres backend not bundled yet (SQLite only) — BACKLOG #8.
- Feeds include past events (archive) with no upcoming-only view yet — BACKLOG #3.
- `selectolax` not in requirements.txt until the first HTML scraper lands.
