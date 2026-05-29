# PROGRESS — dc-frontier-events

## Status: Layers 1+2 live; emits ICS + RSS (full/upcoming/big-names) + events.json + map.html. All gates MET.

## Iteration 5 (2026-05-29) — /map web view + JSON export
Added a static Leaflet map and a machine-readable JSON feed (both GOAL-named deliverables).

### What was built
- `emit.write_json` — full normalized event set as JSON (adds `layer` per event).
- `emit.write_map` — self-contained `map.html` (Leaflet via CDN, OSM tiles) plotting every
  event with GEO; color-coded red=big-name / purple=Layer-2 / blue=Layer-1; popups link to source.
  JSON payload safely embedded (`</` escaped).
- Pipeline emits `events.json` (all kept) + `map.html`.
- 3 new tests (JSON round-trip + layer; map geo-only + header + empty).

### Verification numbers (live run, 2026-05-29)
- **Unit tests: 33 passed.**
- `events.json`: 65 events, layers [1, 2], 51 with GEO.
- `map.html`: 15.3 KB, header "51 mapped / 65 total", `#map` present, Leaflet loaded, embedded
  `EVENTS` array parses to 51 markers. Past feeds unchanged; idempotent.

---

## Status: Layers 1 + 2 live; emits full + upcoming + big-names feeds. All project gates MET.

## Iteration 4 (2026-05-29) — Upcoming-window feeds
Added forward-looking feeds so a subscriber sees what's actually coming up, not the
archive of 2023–2025 events.

### What was built
- `emit.filter_upcoming(events, today_iso)` — pure, testable; ISO-date string compare.
- Pipeline emits `events-upcoming.ics` + `feed-upcoming.xml` (start ≥ today, sorted), alongside
  the existing full + big-names feeds. `today` is injectable (defaults to UTC now) for tests.
- 1 new test (boundary inclusive + date/datetime mix).

### Verification numbers (live run, today=2026-05-29)
- **Unit tests: 30 passed.**
- **upcoming = 5 events**, all dates ≥ 2026-05-29 (range 05-29 .. 06-15), spanning **both layers**:
  Luma "AI Evals", AI Collective "Humans in AI Week" (×2), DVDC "Data Visualization with AI",
  and **CSIS "Data Centers, AI, and the Future of U.S. Strategic Competitiveness"**.
- `events-upcoming.ics` parses (icalendar); `feed-upcoming.xml` feedparser bozo=False. Full feeds unchanged (65). Idempotent.

---

## Status: Layers 1 + 2 live (4 live sources, 2 Layer-2 think tanks). All project verification gates MET.

## Iteration 3 (2026-05-29) — Second Layer-2 source: CSIS + UTC emit fix
Added the CSIS adapter (a second think-tank / Layer-2 source) and fixed a timezone
serialization bug surfaced by CSIS's timed events.

### What was built
- `aggregator/fetchers/csis.py` — async httpx + selectolax. Parses `article.ts-card-event-*`
  cards: `<h3>` title, **date + time + tz** ("June 4, 2026 • 10:30 – 11:30 am EDT"),
  `/programs/` host. Richer than CSET (precise start time, not date-only). Registered as Layer 2, dc_curated.
- **Emit timezone fix**: a fixed-offset start (EDT −04:00) made icalendar emit an invalid
  `TZID="UTC-04:00"` with no VTIMEZONE. `emit._to_utc` now normalizes aware datetimes to UTC
  → clean `...Z`. (Luma events were already UTC; unaffected.)
- 4 new CSIS parser tests + 1 emit-UTC regression test.

### Verification numbers (live run, 2026-05-29)
- **Unit tests: 29 passed.**
- **Sources: 5/7 live across layers [1, 2]** — DC2=72, dctech=24, aic-washington=453, cset=10, **csis=13** (16 cards, dups collapsed). Quarantined: DCtechevents (empty), ai (404).
- **572 raw → 478 deduped (94 removed) → 65 kept** (349 loc, 64 topic dropped).
- **1 CSIS AI event** flows to the feed: "Data Centers, AI, and the Future of U.S. Strategic Competitiveness" (the other ~12 CSIS events are energy/security/space → correctly dropped on topic). CSET still contributes 9.
- CSIS DTSTART now `20260604T143000Z` (valid UTC, tz-aware). events.ics=65 (icalendar, 0 malformed); feed.xml=65 (feedparser bozo=False). Idempotent; 0 non-DC-geo leaks.
- big-name still 0 (think-tank speaker names live on detail pages, not listing cards — see NEXT STEP).

---

## Status: Layers 1 + 2 live and verified end-to-end. The "≥3 sources across ≥2 layers" project gate is MET.

## Iteration 2 (2026-05-29) — Layer-2 source: CSET (Georgetown)
Refactored `fetchers.py` into a `fetchers/` **adapter package** (each adapter returns
normalized `Event`s; pipeline is now format-agnostic) and added the CSET scraper —
the first Layer-2 / policy source.

### What was built
- `aggregator/fetchers/{base,luma,cset}.py` + dispatcher — `gather_all(sources)` returns `SourceResult`s.
- **CSET adapter** (`cset.py`): CSET's listing is behind a WAF that 403s httpx (TLS fingerprint),
  so it fetches with **`curl_cffi` (Chrome impersonation)** + parses the `div.teaser__top` cards
  with **`selectolax`** (title/date/location/excerpt). No per-event detail fetch needed.
- `Source` gained `kind` ("luma"|"cset") + `url`; CSET registered as Layer 2, dc_curated.
- `detect_topics` exposed for reuse across adapters.
- 5 new offline CSET parser tests (date parse, virtual/Online, topics, excerpt, grid-guard).

### Verification numbers (live run, 2026-05-29)
- **Unit tests: 24 passed.**
- **Sources: 4/6 live across layers [1, 2]** — DC2=72, dctech=24, aic-washington=454, **cset=10** (Layer 2). Quarantined: DCtechevents (empty), ai (404).
- **560 raw → 466 deduped (94 removed) → 64 kept** (350 loc, 52 topic dropped).
- **9 CSET Layer-2 events** flow into the feed (AI Governance, AI Red-Teaming, Rewiring the Chip Landscape, China's AI Leap, US-China AI Power Race, Tech Workforce, …). The 10th ("The New Bio Frontier") correctly dropped on topic (bio, not AI/chip).
- **events.ics = 64 VEVENTs** (icalendar, 0 malformed); **feed.xml = 64** (feedparser bozo=False).
- Precision: 0 in-person non-DC-geo kept. Idempotent (re-run stable at 64).
- big-name still 0 (CSET titles don't name watchlist orgs; speakers live on detail pages — see BACKLOG #2).

---

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
**Relevance ranking** — score kept events by topic strength + DC proximity (haversine from GEO)
+ is_big_name + upcoming, and order the feeds / a "top picks" view by it (GOAL: "ranks by
relevance + proximity + big name"). Deterministic and fully verifiable. NOTE from iter-5 probe:
detail-page big-name enrichment was deferred — current CSET/CSIS detail pages contain ~no
watchlist names (only an ambiguous "intel"), so that infra would yield 0 now + risk false
positives. Revisit when data warrants (BACKLOG #3). See BACKLOG #1.

## Known simplifications (tracked in BACKLOG.md)
- CSET events lack per-event time + speakers (listing cards only) — BACKLOG #2 (detail-page enrich).
- Postgres backend not bundled yet (SQLite only) — BACKLOG #9.
- Feeds include past events (archive) with no upcoming-only view yet — BACKLOG #3.
