# BACKLOG — dc-frontier-events (ranked, highest leverage first)

## Done
- ~~Layer-2 CSET (Georgetown) scraper~~ ✅ iteration 2 (curl_cffi + selectolax; 10 events, 9 kept).
- ~~Layer-2 CSIS scraper~~ ✅ iteration 3 (httpx + selectolax, date+time+tz; 13 events, 1 on-topic).
- ~~Emit UTC timezone fix~~ ✅ iteration 3 (aware datetimes normalized to `...Z`).
- ~~Upcoming-window feeds~~ ✅ iteration 4 (`events-upcoming.ics`/`feed-upcoming.xml`; 5 live).
- ~~/map web view + events.json~~ ✅ iteration 5 (Leaflet map, 51 pins; JSON export).
- ~~Relevance ranking~~ ✅ iteration 6 (`rank.py`; `feed-top.xml`; score in JSON/map).
- ~~Weekly digest generator~~ ✅ iteration 7 (`digest.py` → `digest.md`, ranked).
- ~~Generic iCal adapter + GWU (Layer 3)~~ ✅ iteration 8 (3 layers live; 4 big-names surfaced).
- ~~README + CLI~~ ✅ iteration 9 (argparse `--out/--db/--today`; full README).
- ~~Expand + precision-test big-name watchlist~~ ✅ iteration 10 (frontier labs/chip makers/leaders; Intel lookahead).
- ~~Alerting~~ ✅ iteration 11 (`alerts.py`/`alerts.md`; new-since-last-run via store; idempotent).

## Ranked (remaining — several blocked on externals)
1. **Weekly digest *emailer*** — SMTP-send `digest.md`/`alerts.md`. BLOCKED: needs SMTP creds to
   verify sending; the rendered digest/alerts already exist. Wire when creds are provided.
2. **Real Postgres backend** — implement `PostgresStore` behind `open_store()`. BLOCKED: can't
   verify without a reachable `DATABASE_URL`; SQLite fallback works today.
3. **More sources** — additional think tanks (Brookings/ITIF/CNAS/Atlantic Council) + university
   feeds are each bespoke/fragile (probed: most block httpx or export 0 via bare iCal). Add as
   each yields a reliable feed/endpoint.
4. **CSET/CSIS detail-page speaker enrichment** — deferred (iter-5): current detail pages carry
   ~no watchlist names; build when data warrants.
5. **Multi-day series dedupe** — collapse per-day entries of one event (e.g. "AI+EXPO 2026" ×3) into a date range.
6. **Cross-language dedupe; archiving partition; /map clustering & filters; ICS topic-coloring.**
3. **Detail-page speaker enrichment (CSET + CSIS) → big-names.** DEFERRED: iter-5 probe found
   current detail pages carry ~no watchlist names (only ambiguous "intel"); would yield 0 now and
   risk false positives. Build when data warrants; pair with tightening the big-name watchlist
   ("intel"→Intel-the-company only, etc.).
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
