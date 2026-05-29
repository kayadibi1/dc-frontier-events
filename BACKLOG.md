# BACKLOG — dc-frontier-events (ranked, highest leverage first)

## Done
- ~~Layer-2 CSET (Georgetown) scraper~~ ✅ iteration 2 (curl_cffi + selectolax; 10 events, 9 kept).

## Ranked
1. **Layer-2 scraper: CSIS** — `https://www.csis.org/events` (httpx-accessible: 200, ~54 event
   links). Wadhwani AI Center / Strategic Technologies; where Nvidia's Jensen Huang did a
   fireside chat → prime big-name source. Hardens Layer 2 and should yield the first big-name hits.
2. **CSET detail-page enrichment** — fetch each `/event/<slug>/` page for start/end *time*
   (cards are date-only) + speakers/host orgs. Feeds `is_big_name` from speakers (CSET hosts
   OpenAI/Anthropic/NVIDIA policy folks) and gives precise ICS times instead of all-day.
3. **Upcoming-window view** — emit `events-upcoming.ics`/`feed-upcoming.xml` filtered to
   `start >= today`, sorted ascending. Feeds are currently archive-heavy.
4. **Speaker/org NER** — extract `speakers[]` from descriptions ("with X", "fireside with Y")
   across all sources so big-name detection isn't limited to title/desc string matches.
5. **Eventbrite + Meetup adapters** — CSET cross-posts to Eventbrite; Meetup groups expose
   per-group iCal. Real cross-platform dupes → exercises the fuzzy title+date dedupe pass.
6. **Relevance ranking** — score = topic-match strength + DC proximity (haversine from GEO) +
   `is_big_name` weight; expose a ranked top-N (big-names-only variants already emitted).
7. **Brookings + ITIF Layer-2 scrapers** — both httpx-accessible; Brookings exposes JSON-LD
   Event blocks (robust parse). Broadens think-tank coverage.
8. **/map web view** — static HTML + Leaflet plotting kept events by GEO (DCtechevents has /map).
9. **Real Postgres backend** — implement `PostgresStore` behind `open_store()` when
   `DATABASE_URL` + `psycopg` are present; schema/upsert parity with SQLite.
10. **Stale-event reconciliation** — events that fall out of the filter or whose date passed
    move to an archive partition; keep the active feed lean.
11. **Self-healing Luma cal-id resolver** — resolve `lu.ma/<slug>` → `cal-id` at runtime
    (the `ai` calendar 404'd; `DCtechevents` returned empty).
12. **Weekly DC AI/chip digest emailer** — render new + upcoming big-name events to a digest.
13. **University Layer-3 feeds** — JHU/SAIS, Georgetown, GWU, GMU/Mercatus (Localist/Trumba).
14. **Alerting** — notify when a watchlisted org/person is newly announced on any source.
15. **The Hill / NIST-CAISI** — congressional committee hearing schedules + NIST events.
