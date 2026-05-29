# dc-frontier-events

A production-grade aggregator that pulls **AI, semiconductor, and frontier-tech events** in the
Washington, DC metro into a single, deduplicated, **relevance-ranked** feed — with first-class
attention to "big name" events (Anthropic, OpenAI, Nvidia, Microsoft, …) and the policy / think-tank
venues where those names actually appear in DC.

See [`GOAL.md`](GOAL.md) for the mission and [`PROGRESS.md`](PROGRESS.md) for the latest verified run.

## Why three layers
The marquee AI/chip events in DC mostly do **not** live on community calendars. The aggregator
ingests all three layers so it doesn't miss the events that matter most:

| Layer | What | Sources wired |
|------:|------|---------------|
| **1 — builder/community** | native iCal community calendars | Luma: DC Data & AI, DC Tech Events, DC Tech & Venture, AI Collective DC, global AI |
| **2 — policy / big-name** | think tanks (HTML scrape) | **CSET** (Georgetown), **CSIS** |
| **3 — university** | campus event calendars (iCal) | **GWU** (Localist) |

Empty or failed sources are **quarantined and logged, never faked** (e.g. a 404 or an empty feed
is reported, not silently dropped).

## Pipeline
```
fetch (per-source adapter) → normalize → dedupe → filter → rank → store → emit
```
- **fetch** — `aggregator/fetchers/` adapters: `luma`/`ics` (httpx + icalendar), `cset`
  (curl_cffi browser-TLS impersonation + selectolax), `csis` (httpx + selectolax). Each returns
  already-normalized `Event`s.
- **normalize** — one schema (`aggregator/models.Event`): id, title, start/end/tz, venue/address,
  lat/lng (GEO), organizer, speakers, source, source_url, topics, is_big_name, raw.
- **dedupe** — exact-UID (same event cross-listed) + fuzzy title-within-day (`difflib`).
- **filter** — keep iff `(DC-metro OR virtual-from-a-DC-curated-source) AND (on-topic OR big-name)`.
  **GEO is authoritative for in-person events** (a real out-of-DC coordinate excludes, regardless
  of incidental "VA"/"Washington" text). Sets `is_big_name` from the config watchlist.
- **rank** — `score = topic strength + big-name + upcoming + DC proximity (haversine)`.
- **store** — idempotent SQLite upsert (Postgres-ready interface); never blocked on infra.
- **emit** — see Outputs.

## Outputs (written to `out/`)
| file | what |
|------|------|
| `events.ics` / `feed.xml` | full deduped+filtered set (iCalendar / RSS 2.0) |
| `events-upcoming.ics` / `feed-upcoming.xml` | events with start ≥ today |
| `feed-top.xml` | top-25 upcoming, relevance-ranked |
| `events-big-names.ics` / `feed-big-names.xml` | watchlist-only variant |
| `events.json` | machine-readable export (incl. `layer`, `score`) |
| `map.html` | self-contained Leaflet map of all GEO events (color-coded by layer / big-name) |
| `digest.md` | ranked weekly digest (foundation for an emailer) |

## Install & run
```bash
pip install -r requirements.txt
python -m aggregator                       # writes feeds to ./out, db at ./data/events.db
python -m aggregator --out site --db /var/lib/dcfe.db
python -m aggregator --today 2026-06-01    # override the upcoming/ranking window
```
Requires Python 3.11+. Postgres is optional (`DATABASE_URL`); it falls back to SQLite so a run is
never blocked on infra. Re-runnable and idempotent (each run re-fetches and upserts; feeds reflect
the fresh fetch, the SQLite store is the durable archive).

## Tests
```bash
python -m pytest tests/ -q     # offline, deterministic (parsers / dedupe / filter / rank / emit / digest)
```

## Configuration
Sources, the topic keyword set, the big-name watchlist, and the DC bounding box / text matchers all
live in [`aggregator/config.py`](aggregator/config.py). Add a Luma calendar or any iCal feed with one
line; add a think-tank scraper as a new `fetchers/<name>.py` adapter registered in `fetchers/__init__.py`.

## Project layout
```
aggregator/
  config.py        sources, watchlists, topic + DC matchers
  models.py        the normalized Event schema
  fetchers/        ics, luma, cset, csis adapters + dispatcher
  normalize.py     iCal VEVENT -> Event (+ topic detection)
  dedupe.py        exact-UID + fuzzy dedupe
  filter.py        DC + topic + big-name relevance
  rank.py          relevance scoring
  storage.py       idempotent SQLite store
  emit.py          ICS / RSS / JSON / map writers
  digest.py        ranked markdown digest
  pipeline.py      orchestration + concrete-count logging
tests/             offline unit tests
```
