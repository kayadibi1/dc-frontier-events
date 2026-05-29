# BACKLOG — dc-frontier-events (ranked, highest leverage first)

1. **Layer-2 scraper: CSET (Georgetown) events** — `https://cset.georgetown.edu/events/`.
   Async `httpx` + `selectolax`. Satisfies the unmet gate "≥3 sources across ≥2 layers"
   AND surfaces the first real DC big-name policy events. Add `selectolax` to requirements.
   New `fetchers/` package: split `fetchers.py` into `luma.py` + `cset.py` behind a common adapter.
2. **Layer-2 scraper: CSIS events** — `https://www.csis.org/events` (Wadhwani AI Center,
   Strategic Technologies). Where Nvidia's Jensen Huang did a fireside chat — prime big-name source.
3. **Upcoming-window view** — emit `events-upcoming.ics`/`feed-upcoming.xml` filtered to
   `start >= today`, sorted ascending. Current feeds are archive-heavy (many 2024 events).
4. **Speaker/org NER** — extract `speakers[]` from descriptions ("with X", "featuring Y",
   "fireside with Z") so `is_big_name` can fire on speakers, not just title/desc text.
5. **Eventbrite + Meetup adapters** — CSET cross-posts to Eventbrite; Meetup groups expose
   per-group iCal. Real cross-platform dupes → exercises the fuzzy title+date dedupe pass.
6. **Relevance ranking** — score = topic-match strength + DC proximity (haversine from GEO) +
   `is_big_name` weight; expose a ranked top-N and a `big-names-only` view (variants already emitted).
7. **/map web view** — static HTML + Leaflet plotting kept events by GEO (DCtechevents has a /map).
8. **Real Postgres backend** — implement `PostgresStore` behind `open_store()` when
   `DATABASE_URL` + `psycopg` are present; schema/upsert parity with SQLite.
9. **Stale-event reconciliation** — events that fall out of the filter (bug fix, removed upstream)
   or whose date has passed should move to an archive partition; keep the active feed lean.
10. **Self-healing Luma cal-id resolver** — resolve `lu.ma/<slug>` → `cal-id` at runtime so
    config survives id changes (the `ai` calendar 404'd; `DCtechevents` returned empty).
11. **Weekly DC AI/chip digest emailer** — render new + upcoming big-name events to a markdown/email digest.
12. **University Layer-3 feeds** — JHU/SAIS, Georgetown, GWU, GMU/Mercatus (Localist/Trumba iCal+RSS).
13. **Alerting** — fire a notification when a watchlisted org/person is newly announced on any source.
14. **The Hill / NIST-CAISI** — congressional committee hearing schedules + NIST events (testimony-adjacent).
