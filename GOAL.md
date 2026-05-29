# GOAL — DC AI & Semiconductor Event Aggregator (`dc-frontier-events`)

## Mission
Build and continuously improve a production-grade aggregator that pulls AI, semiconductor,
and frontier-tech events / workshops in the Washington, DC metro into a single, deduplicated,
ranked feed — with first-class attention to "big name" events (Anthropic, OpenAI, Nvidia,
Microsoft, and the people who run them) and to the policy / think-tank venues where those
names actually appear in DC.

**This file is the source of truth. Every loop iteration reads it first.**

## Why this is non-obvious
The marquee AI/chip events in DC mostly do NOT live on Luma/Meetup — those cover the
builder/community layer. The high-signal events (fireside chats, policy launches,
testimony-adjacent panels) happen at think tanks and at the companies' own DC offices.
The aggregator must cover all three layers or it misses the events that matter most.

## Source layers (ingest all three)

### Layer 1 — Builder / community (native iCal, trivially mergeable)
Each public Luma calendar exposes an "Add iCal Subscription" `.ics` URL. Subscribe + parse:
- `https://lu.ma/DC2`            — DC Data & AI Events (Data Community DC)
- `https://lu.ma/DCtechevents`   — Washington DC Tech Events (has a `/map` view)
- `https://lu.ma/dctech`         — DC Tech & Venture Coalition
- `https://lu.ma/aic-washington` — AI Collective DC
- `https://lu.ma/ai`             — global AI calendar (Claude Community, Latent.Space) → filter to DC
- Meetup: Data Science DC and siblings (per-group iCal export)

### Layer 2 — Policy / big-name (mostly scrape; the high-signal tier)
- **CSET (Georgetown):** `https://cset.georgetown.edu/events/` (also cross-posts to Eventbrite). The AI+semiconductor policy shop.
- **CSIS:** `https://www.csis.org/events` (Wadhwani AI Center, Strategic Technologies, Intelligence/NatSec & Tech). Where Nvidia's Jensen Huang did a fireside chat.
- Brookings, CNAS, ITIF, Atlantic Council (GeoTech), Carnegie, RAND, Hudson, SCSP; SIA for chips specifically.
- **Company DC offices:** OpenAI "The Workshop" (901 F St NW demo space), Anthropic DC office / event weeks, Microsoft DC, Nvidia (guest appearances).
- **The Hill + NIST/CAISI:** congressional committee hearing schedules (congress.gov + committee sites), NIST events.

### Layer 3 — University (local; many expose iCal AND RSS per category via Localist/Trumba)
- JHU / SAIS, Georgetown, GWU, GMU / Mercatus — subscribe to their tech/AI category feed where available, else scrape.

## Architecture (target)
- **Language:** Python 3.11+. Async fetchers with `httpx`; HTML parsing with `selectolax`. (Mirrors the operator's existing scraper stack.)
- **Storage:** Postgres if reachable via `DATABASE_URL`; otherwise fall back to local SQLite so the loop is NEVER blocked on infra.
- **Pipeline:** `fetch` (per-source adapter) → `normalize` → `dedupe` → `filter` → `emit`.
  - **Normalize** to one schema: `id, title, description, start, end, tz, venue_name, address, lat, lng, organizer, speakers[], source, source_url, topics[], is_big_name, raw`.
  - **Dedupe:** the same event appears on Luma + Eventbrite + the org page. Key on a fuzzy match of (normalized title + date + venue/city).
  - **Filter:** keep events that are (DC-metro OR virtual-from-a-DC-org) AND (topic ∈ {AI, ML, semiconductor, chips, compute, export controls, GPU, datacenter, …} OR organizer/speaker matches the named-org/person watchlist).
  - **is_big_name:** title/desc/speakers/org match {Anthropic, OpenAI, Nvidia, Microsoft, Dario Amodei, Sam Altman, Jensen Huang, Brad Smith, Jack Clark, …}. Keep the watchlist in a config file.
- **Emit:** a unified `events.ics` (valid iCalendar) AND a `feed.xml` (valid RSS or Atom). Optionally a "big-names-only" variant of each.
- **Scheduling:** re-runnable idempotently (each run upserts; emitted feeds are regenerated).

## Verification gates (a feature is NOT "done" until ALL pass)
- Unit tests for parsers / normalizer / dedupe / filter pass.
- A live end-to-end run fetches real events from **≥ 3 sources across ≥ 2 layers**.
- `events.ics` parses with the `icalendar` library; `feed.xml` parses with `feedparser`.
- Reported, concrete counts logged: total events, per-source counts, # deduped, # big-name.
- No tracebacks; an empty result from a source is logged and quarantined, never silently dropped, and **never replaced with fake data**.

## Definition of an ambitious finished state (what to expand toward)
A self-updating service that aggregates all three layers; ranks by relevance + proximity +
"big name"; emits `.ics`/RSS plus a small `/map` web view; sends a weekly DC AI/chip digest;
supports a "big names only" filter; archives past events; and alerts when a watchlisted
org/person is announced. The loop should keep climbing this ladder and inventing rungs beyond it.

## Phase ladder (rough — the loop decides specifics each iteration)
1. Repo + schema + SQLite + one real Luma `.ics` adapter, emitting a valid `.ics` end-to-end. **Prove the spine.**
2. All Layer-1 Luma adapters + dedupe + RSS emit + tests.
3. Layer-2 scrapers (start with CSET + CSIS) + the named-org/speaker filter + `is_big_name`.
4. Layer-3 university feeds; Eventbrite + Meetup; Hill hearings.
5. Ranking, `/map` web view, digest emailer, alerting, archiving — then the 10x ideas from `BACKLOG.md`.

## Operating principles
Real data only. Verified before "done." Idempotent + re-runnable. Disk is the only memory
across iterations (code + `PROGRESS.md` + `BACKLOG.md` + git).
