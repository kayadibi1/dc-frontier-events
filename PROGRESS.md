# PROGRESS — dc-frontier-events

## Relevance precision II (2026-05-30) — per-source title-topic strictness
User decision "tighten, keep both": the two firehose sources (gwu = whole-campus calendar,
aic-washington = global org feed) now require the topic to appear in the TITLE; a description-only
keyword there is boilerplate. Curated Layer-2 think tanks (CSET/CSIS/Brookings) stay lenient so
their desc-only gems survive (e.g. CSET "How the U.S. Wins the Global Tech Competition", "The Talent
Map"). `config.STRICT_TITLE_TOPIC_SOURCES` + `filter._has_qualifying_topic`.
- Live before/after: kept 83 -> 78; the 5 newly-dropped are all GWU loose-desc noise (InnovationFest,
  GWebinar: practical wisdom?, The Future of Medicine, Animals Tech & Law, JUXTAPOSITION). Verified:
  0 kept strict-source events lack a title topic; all marquee events preserved (Data Centers AI,
  economic mobility, Rewiring the Chip, AI+EXPO, Data Viz with AI); admin noise still absent.
- **95 unit tests pass** (+4 strict-source tests, incl. a curated-source-keeps-desc-only guard).

## Relevance precision (2026-05-30) — kill admissions/boilerplate noise
The upcoming feed was crowded with university admin events (GW Nursing Tour, GWSB info sessions,
Grocery Retail Summit). Diagnosed by printing the exact regex hit per kept event — two root causes:
1. `compute` topic's bare `accelerat` matched "**accelerat**ed MBA / **Accelerat**or Alumni /
   **Accelerat**ing Warfighting" → tightened to `\baccelerators?\b|accelerated comput` (real senses).
2. Admissions/recruitment events match real topics but are marketing → new title-only
   `ADMIN_EXCLUDE_PATTERN` (info session, open house, why gw, master of, MBA/graduate program,
   nursing/campus tour, commencement, application deadline) + `filter.is_admin_event` (dropped early,
   tracked as `dropped_admin`).
- **Before/after diff (real data): dropped 26, added 0** — every drop genuine noise (incl. "LLM
  Virtual Webinars: Why GW **Law**" = Master of Laws, not the AI sense). Zero real events lost;
  marquee events verified present (Data Centers AI/CSIS, economic mobility/Brookings, Data Viz with
  AI, Rewiring the Chip). kept 109 → **83**; upcoming list is now genuinely high-signal.
- **91 unit tests pass** (+6 precision). E2E 32/32 incl. new guards: "no admin/recruitment noise in
  output" + "real marquee events still present".

## BUG FIX (2026-05-30) — dead dedupe passes (found by inspecting real output)
`aggregator/dedupe.py` had **two `dedupe()` definitions**; the second (an old 2-pass: exact-id +
fuzzy only) shadowed the full 4-pass version, so **pass 3 (F1 multi-day series collapse) and pass 4
(P3 paraphrase collapse) were silently dead in the live pipeline** — a leftover from the P3 rewrite.
Symptom (visible only in the actual output, not structural checks): GW's "AI+EXPO 2026" appeared as
3 separate rows / 3 "big-name" alerts instead of one collapsed multi-day event.
- Fix: deleted the stale second definition. Now one `dedupe`, all 4 passes run.
- Verified: fresh run kept 109 → **99** (dedupe removed 276 → 311 as the collapse passes re-engage);
  events.json **99 rows / 99 unique ids / 0 duplicates**; AI+EXPO = **1 row** (range 05-07→05-09),
  1 big-name alert. **86 unit tests pass.** E2E 33/33 incl. NEW regression guards: no duplicate ids
  in events.json **or** events.ics, and an explicit "AI+EXPO collapsed to 1" assertion.
- LESSON: structural E2E (parses, parity, counts) was all green while two features were dead —
  duplicate rows are still individually valid. Inspecting the real product content caught it.

## Fix (2026-05-30) — alerts now itemize ALL new events ("as they are added")
Surfaced by inspecting the real product output (not just structural checks): `alerts.md` detected
the right count of new-since-last-run events but only **listed** big-name ones — regular new events
showed as a bare number. Now `build_alerts` itemizes every newly-added event (⭐ big-names first,
then a `🆕 New events since last run (N)` list with date · title · source · topics · link); the
first/baseline run still suppresses the full dump.
- Demonstrated with real data: seed DB → delete 2 upcoming AI events → re-run → alerts lists exactly
  those 2 ("Online: A gentle intro to AI Evals…", "Tysons Investor Network: AI & The Future…").
- **85 unit tests pass** (+1). Full E2E 31/31 (incl. baseline-note → detects-new → itemizes-new →
  idempotent-0). NEW STANDING ROUTINE: run a full end-to-end check after each implementation.

## Source add (2026-05-30) — Brookings (Layer 2), verify-first
Added Brookings after a strict step-by-step, verify-before-commit redo (an earlier Hudson + first
Brookings attempt were both committed-then-reverted with false event claims; this time every step
was confirmed against real output first). `fetchers/brookings.py` (httpx) parses `article` cards:
title in a heading, date as free text ("June 10 2026" / "July 15, 2026"), `a[href*='/events/']`
link; sub-brand `/event/` links and undated cards excluded. Brookings HQ in DC → dc_curated.
- **Verified empirically:** live fetch = 14 event cards (3 on-topic AI) → real adapter vs the saved
  real fixture = 14 parsed / 3 on-topic, all unique ids → 3 unit tests → full suite **84 passed**.
- Live: `brookings (layer 2): 14 events` → **9/11 sources live**; kept 106 → **109** (+3 AI:
  "AI and economic mobility" 2026-06-10 upcoming; "AI companion bots…" 2026-05-26; "AI in the
  nursery" 2026-05-18).
- **Output parity confirmed (the earlier "108/107 mismatch" was a phantom of a flaky shell):**
  events.json == events.ics == **109**, 0 malformed, feed.xml + feed-upcoming bozo=0; the upcoming
  AI event is in events-upcoming.ics, the two past ones are not.
- Hudson stays deferred (current listing has 0 AI events; see BACKLOG).

## Status: Enhancement portfolio (autonomous) COMPLETE — F1–F7 done. GOAL ladder + final verification already PASSED.
Design: docs/superpowers/specs/2026-05-29-aggregator-enhancements-design.md

## Implementation plans written (2026-05-29) for the remaining backlog — `docs/superpowers/plans/`
Via the writing-plans skill, one plan per remaining subsystem (TDD, bite-sized, real code):
P1 speaker-enrichment · P2 more-sources · P3 crosslang-dedupe · P4 archiving-partition ·
P5 ics-enrichment · P6 live-ops-runbook.

## Executing the plans autonomously (2026-05-29/30)
### P1 speaker-enrichment — DONE
`aggregator/enrich.py`: `extract_speakers` (structured `[class*=name]` nodes + prose "featuring X
and Y" fallback) and async `enrich_layer2` over Layer-2 detail pages (curl_cffi for cset, httpx
else; best-effort). Pipeline runs it after fetch (before dedupe); `--no-enrich` skips it.
**Precision (key design):** `speakers[]` rejects org/affiliation strings via an org-word stoplist;
big-name flagging matches orgs+people against the event's own text but **only watchlisted PEOPLE
against speakers** — a panelist's employer must not make it a "Microsoft event".
- **68 unit tests pass.** Live (verified from events.json): enrichment runs; speakers extracted
  from ~13 Layer-2 events. **big-name = 3, ALL via the event's own text** (Microsoft/Amazon,
  Anthropic, Databricks); the speaker path found **no watchlisted person** in current CSET/CSIS
  data — same honest "build when data warrants" finding as the iter-5 probe. The machinery is
  correct + safe: the earlier false positive ("Microsoft AR" affiliation) is eliminated by the
  person-only speaker match.
- HONESTY CORRECTION: an earlier draft of this section (and the `7ae291a` commit message) wrongly
  claimed big-name=4 with "Jack Clark surfaced via speaker." That did NOT happen — actual is
  big-name=3, none via speaker. Extraction on CSET is also still noisy (org/role strings reach
  `events.json` `speakers[]`; harmless to correctness, a quality TODO).
- NOTE: the first P1 commit (`0562598`) landed with a failing prose test (a batch-ordering
  mistake); fixed in `7ae291a`.

### P3 cross-language/fuzzy dedupe — DONE
Dedupe pass 4: order-insensitive token-set Jaccard (`_token_set_ratio`, threshold 0.7) with a
haversine location guard (`_near`, ≤3 km or missing geo) so same-day paraphrase/reorder dupes
collapse but two distinct same-day events at different venues never merge. Optional import-guarded
`semantic_ratio` (sentence-transformers) is a clean no-op when the lib is absent.
- **72 unit tests pass** (+5: token-set order-insensitivity/low-distinct, paraphrase same-geo
  collapse, far-apart kept, semantic no-op). Live: dedupe removed 278 → **280** (2 more paraphrase
  dupes collapsed); no over-merge.

### P4 archiving partition + pruning — DONE
Added a `status` column (active/archived) with safe migration (and `Event.from_row` now pops it —
the coupled change that, when missed, throws `TypeError`). `Store`+`PostgresStore` gained
`mark_archived(active_ids)` (demote all → re-mark this run's ids active), `active_events`,
`archived_events`, and `prune(before_iso)` (delete archived rows older than a cutoff). Pipeline
calls `mark_archived` + `prune(today−730d)` after upsert and prints a `partition:` line.
- **76 unit tests pass** (+3: status active, partition, prune). Live: `partition: active=107
  archived=0 pruned=0`; run 2 idempotent (0 new); `events-archive.ics`=107 VEVENTs.

### P5 ICS enrichment (COLOR + VALARM) — DONE
`emit.write_ics` now adds a per-event RFC-7986 `COLOR` (red=big-name / purple=L2 / green=L3 /
blue=L1) and, when given `today_iso`, a 1-day `VALARM` reminder on upcoming events. The param
defaults to `None` (no alarms) so existing callers/tests are unaffected; the pipeline passes
`today` to the events / upcoming / big-names / archive ICS writers.
- **79 unit tests pass** (+3: per-event color, VALARM-only-for-upcoming, no-alarm-without-today).
  Live: COLOR on all 107 VEVENTs; **23 VALARMs == 23 upcoming**; events.ics reparses (0 malformed).

### P2, P6 — pending execution.

## Enhancement F7 (2026-05-29) — More Luma sources
Probed candidate DC AI/tech Luma slugs; added the two that resolved to live feeds:
**AI Tinkerers DC** (`cal-QhC1Y2193RQ7sZ6`, 15) and **DC Tech Meetup** (`cal-GzmqNpNKPBSmYdl`, 16),
both dc_curated single-city chapters.
- **59 unit tests pass.** Now **8/10 sources live**. raw 1164 → 886 deduped → **106 kept**.
  AI Tinkerers added **+3 net** DC AI events incl. a **Databricks** big-name (2→3 big-name, all legit).
  DC Tech Meetup: 10 dropped on topic, its AI events are cross-listed dupes → 0 net (dedup working;
  kept for future unique events). All 8 feeds parse (0 malformed / bozo=False).

## Enhancement F6 (2026-05-29) — Archive feed + last_seen tracking
Added `first_seen`/`last_seen` columns (safe migration for existing DBs); upsert is now
`INSERT … ON CONFLICT(id) DO UPDATE` preserving `first_seen` and refreshing `last_seen` (both
SQLite + Postgres). Pipeline emits `events-archive.ics` from the durable store and reports
`gone-from-sources` (stored ids not in this run's kept).
- **59 unit tests pass** (+1: first_seen preserved / last_seen refreshed). Live: `events-archive.ics`
  103 VEVENTs (parses); gone=0; run 2 idempotent (0 new). 13 output artifacts.

## Enhancement F5 (2026-05-29) — Postgres backend + fallback
`storage.PostgresStore` (psycopg2): same COLUMNS/Event round-trip as SQLite, `INSERT … ON CONFLICT
(id) DO UPDATE` upsert, `RealDictCursor` reads. `open_store` selects Postgres when `DATABASE_URL` is
set AND connectable, else logs + falls back to SQLite (never raises).
- **58 unit tests pass** (+3): default→sqlite; `DATABASE_URL` unreachable→sqlite fallback (no raise);
  SQLite round-trip + idempotent upsert. Live still selects SQLite (no `DATABASE_URL`).
- HONEST: live Postgres path needs a reachable server (psycopg v3 absent; built on psycopg2). The
  verified parts are selection/fallback + schema/SQL parity with the SQLite store.

## Enhancement F4 (2026-05-29) — Pluggable notifier / emailer
`aggregator/notify.py`: `build_message` (HTML digest body + plain-text alt; Subject with counts) +
`deliver` — sends via SMTP+STARTTLS when `SMTP_HOST/USER/PASS/TO` env are set, else **dry-run** writing
`out/email/digest-<today>.eml`. Never blocks (falls back to dry-run on send failure). Stdlib only.
- **55 unit tests pass** (+2). Live: dry-run wrote a valid `.eml` (re-parsed: Subject + 4.7 KB HTML
  digest body). The GOAL's "weekly emailer" is code-complete; real sending just needs SMTP env.

## Enhancement F3 (2026-05-29) — HTML digest
`digest.render_html(events, today)` → self-contained inline-CSS `digest.html` (header + counts,
⭐ Big-names section, ranked Top-upcoming list with date/title/source/topics/score/link). Pipeline
writes it alongside `digest.md`; reused as the email body in F4.
- **53 unit tests pass.** Live `digest.html` (~4.8 KB) parses, self-contained `<style>`,
  headings "Big names" + "Top upcoming (15)". (Big names shows upcoming only → 0 right now.)

## Enhancement F2 (2026-05-29) — Interactive map UX
Rebuilt `map.html` into a filterable, searchable explorer: a server-rendered sidebar list (one `<li>`
per event with data-attributes) synced to a clustered Leaflet map. Controls: layer (L1/L2/L3),
big-names-only, upcoming-only, search; JS filters list + markers together; click a list row to fly to
its pin. MarkerCluster via CDN; fully self-contained.
- **52 unit tests pass.** Live `map.html` (~49 KB): 103 list items, 65 geo pins, all controls present,
  clustering active; non-geo events appear in the list (not as pins).

## Enhancement F1 (2026-05-29) — Multi-day series dedupe
Dedupe pass 3 collapses a single event listed once-per-consecutive-day (same source + source_url +
title, gap ≤ 2 days) into one event spanning the range; weekly/recurring (>2-day gaps) stay separate.
- **52 unit tests pass** (+3). Live: dedupe removed 106 → **264** (GWU multi-day events collapse);
  kept 109 → 103; big-name 4 → **2** (AI+EXPO 2026 triplicate → one event, 05-07..05-09, `raw.days`).

---

## Iteration 12 (2026-05-29) — Final end-to-end verification + FINAL_REPORT.md
Comprehensive fresh run asserting every gate and all 11 output artifacts.
- **49 unit tests pass.** 6/8 sources across layers [1,2,3]; 1133 raw → 1027 deduped → 109 kept;
  4 big-name; 28 upcoming; 69 map pins; idempotent.
- **All 11 artifacts validated PASS**: ICS (0 malformed), 4× RSS (bozo=0), upcoming all ≥ today,
  big-names ★-marked, JSON scored+layered (layers 1,2,3), map+Leaflet, digest + alerts non-empty.
- Wrote `FINAL_REPORT.md` (GOAL-ladder coverage, metrics, honest remaining-work notes).

---

## Iteration 11 (2026-05-29) — Alerting (new-since-last-run)
Made the persistent store productive: detect events new since the last run and alert on
newly-announced big-name events (GOAL: "alerts when a watchlisted org/person is announced").

### What was built
- `Store.existing_ids()` — ids known before this run.
- `aggregator/alerts.py` — pure `build_alerts(new, new_big, today, first_run)` → `alerts.md`.
- Pipeline captures `prior_ids` before upsert, diffs `emitted` against it, writes `out/alerts.md`,
  logs "new since last run / new big-name".
- 4 new tests (alert render: new/empty/first-run; store `existing_ids` persistence across reopen).

### Verification (live, 2026-05-29)
- **Unit tests: 49 passed.**
- RUN 1 (fresh db): 109 new, **4 new big-name** → `alerts.md` baseline note + lists the 4 big-name events.
- RUN 2 (same db): **0 new, 0 new big-name** — idempotent diff confirmed.

---

## Iteration 10 (2026-05-29) — Expand + precision-harden the big-name watchlist
Broadened the watchlist (frontier labs, chip makers, leaders + DC policy figures) while
hardening precision so common phrases don't false-trigger.

### What was built
- Added orgs (Amazon/AWS, Mistral, Cohere, Hugging Face, Scale AI, Databricks, Palantir, TSMC,
  ASML, Qualcomm, Broadcom, IBM) and people (Pichai, Nadella, Hassabis, Lisa Su, Raimondo).
- **Precision**: "Intel" no longer matches "intel community/officer/agency/…" (negative lookahead)
  or "intelligence"; deliberately did NOT add bare "google"/"meta"/"apple" (would match
  "Google Form"/"metadata"/"Big Apple").
- 2 new tests: 5 must-not-match phrases; 4 must-match new names.

### Verification (live, 2026-05-29)
- **Unit tests: 45 passed.** big-name events stable at **4 legit** (no false-positive inflation);
  "AI+EXPO 2026" now also tags **Amazon/AWS** ("Microsoft, Google, Meta, AWS"). layers [1,2,3]; idempotent.

---

## Iteration 9 (2026-05-29) — Operability: CLI + README
Rounded out production-readiness. (Probed Georgetown/GMU/UMD/Howard/American Localist feeds for
more Layer-3 coverage — none export a usable bare iCal; GWU remains the working university feed.)

### What was built
- `python -m aggregator` now has an argparse CLI: `--out DIR`, `--db PATH`, `--today YYYY-MM-DD`
  (overrides the upcoming/ranking window). `pipeline.run` already accepted these.
- `README.md` — documents the 3 layers + sources, the pipeline, all 10 output artifacts, install/run,
  tests, configuration, and project layout.

### Verification (2026-05-29)
- **Unit tests: 43 passed.** `--help` renders; `--out _site` writes all 10 feeds to `_site/`;
  `--today 2030-01-01` → upcoming=0 (override works); layers [1,2,3].

---

## Iteration 8 (2026-05-29) — Generic iCal adapter + GWU (Layer 3) → 3 layers + first big-names
A single generic iCal adapter unlocked a Layer-3 university feed, which lifted coverage sharply
and surfaced the first real big-name events.

### What was built
- `aggregator/fetchers/ics.py` — generic `fetch_ics_url(source, url, ua)` (+ `fetch_ics` for
  `kind="ics"`). Luma adapter refactored to a thin wrapper over it.
- `parse_ics` now reads the iCal `URL:` property for `source_url` (Localist/standard iCal).
- Registered **GWU** (`calendar.gwu.edu/calendar.ics`, Localist) as a Layer-3, dc_curated source.
- 1 new test (URL-property → source_url).

### Verification numbers (live run, 2026-05-29)
- **Unit tests: 43 passed.**
- **Sources: 6/8 live across layers [1, 2, 3]** — +gwu=561 events. 1133 raw → 1027 deduped (106 removed) → **109 kept** (366 loc, 552 topic dropped).
- **big-name events: 4** (first non-zero!) — all validated real (not false positives):
  "AI+EXPO 2026" → Microsoft ("exhibitors including Microsoft, Google, Meta…"); "Vibe Coding to
  Drive Revenue" → Anthropic ("using Claude…").
- **upcoming: 28** (was 5); map pins 69; events.ics=109 (icalendar, 0 malformed); feed.xml=109 (feedparser bozo=False). Idempotent.

---

## Iteration 7 (2026-05-29) — Weekly digest generator
Added a ranked, human-readable digest (foundation for the GOAL's weekly emailer).

### What was built
- `aggregator/digest.py` — pure `build_digest(events, today, top_n)` → markdown: header with
  upcoming/source counts, a ⭐ Big-names section, and a ranked Top-upcoming list (date, title,
  source name, location, topics, score, details link).
- Pipeline writes `out/digest.md`. 3 new tests (ranked order + past-excluded; big-names present/absent; empty).

### Verification numbers (live run, 2026-05-29)
- **Unit tests: 42 passed.**
- `digest.md` lists 5 upcoming events across 3 sources, ranked; CSIS "Data Centers, AI…" first
  (score 36.0). Big-names section shows the explanatory placeholder. Idempotent.

---

## Iteration 6 (2026-05-29) — Relevance ranking
Added scoring so the feed surfaces the most relevant events first (GOAL: "ranks by
relevance + proximity + big name").

### What was built
- `aggregator/rank.py` — pure `score_event(ev, today)` = topic strength (8/topic) + big-name (50)
  + upcoming (20) + DC proximity (haversine from downtown, up to 5, decaying to 0 by ~40km).
  `top_upcoming(events, today, n)` returns the ranked forward list.
- Pipeline stamps `raw["score"]` on every emitted event, emits `feed-top.xml` (top 25 upcoming).
- `score` surfaced in `events.json` and map popups.
- 6 new ranking tests (big-name/upcoming/topic-count/proximity ordering; big: tags excluded; top sort).

### Verification numbers (live run, 2026-05-29)
- **Unit tests: 39 passed.**
- `events.json`: 65/65 events scored. `feed-top.xml`: 5 upcoming entries, **strictly descending by score** (verified).
- Top pick = CSIS Layer-2 "Data Centers, AI, and the Future of U.S. Strategic Competitiveness" (36.0),
  then geo-bonused DC community events (32.3, 32.1, 28, 28). Idempotent; other feeds unchanged.

---

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
**Final end-to-end verification pass + FINAL_REPORT.md.** The full GOAL "ambitious finished state"
ladder is now realized (3 layers; rank; ICS/RSS/JSON/map/digest/alerts; archive via store). Do a
comprehensive fresh run asserting every gate + every output artifact, and write FINAL_REPORT.md.
Remaining backlog items are blocked on externals (Postgres needs a DB; emailer needs SMTP creds)
or are fragile (more scraped think-tank/university sources) — pursue when those constraints lift.

## Known simplifications (tracked in BACKLOG.md)
- CSET events lack per-event time + speakers (listing cards only) — BACKLOG #2 (detail-page enrich).
- Postgres backend not bundled yet (SQLite only) — BACKLOG #9.
- Feeds include past events (archive) with no upcoming-only view yet — BACKLOG #3.
