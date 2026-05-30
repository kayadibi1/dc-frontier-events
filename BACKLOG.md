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

### Enhancement portfolio (autonomous; spec: docs/superpowers/specs/2026-05-29-aggregator-enhancements-design.md)
- ~~F1 multi-day series dedupe~~ ✅ (pass 3; AI+EXPO 3→1; 264 dupes removed).
- ~~F2 interactive map UX~~ ✅ (filter/search/cluster; sidebar list synced to map).
- ~~F3 HTML digest~~ ✅ (`render_html` → `digest.html`, self-contained).
- ~~F4 pluggable emailer~~ ✅ (`notify.py`; dry-run `.eml`, SMTP when env set).
- ~~F5 Postgres backend + fallback~~ ✅ (`PostgresStore`/psycopg2; selection+fallback tested; live needs a server).
- ~~F6 archive feed + last_seen~~ ✅ (`events-archive.ics`; ON CONFLICT upsert; gone-from-sources report).
- ~~F7 more Luma sources~~ ✅ (added AI Tinkerers DC +3 incl. Databricks big-name; DC Tech Meetup).

**Enhancement portfolio COMPLETE (F1–F7).** Remaining ideas below are blocked on externals or are future polish.

## Ranked (genuinely remaining after the 12 iterations + F1–F7 portfolio)
Implementation plans for these live in `docs/superpowers/plans/`; execution status in PROGRESS.md.
- ~~CSET/CSIS detail-page speaker enrichment~~ ✅ executed P1 (machinery + person-only big-name match; live data has no watchlisted speakers yet).
- ~~Cross-language / fuzzy dedupe~~ ✅ executed P3 (token-set pass 4 + optional embeddings).
- ~~Archiving partition + store pruning~~ ✅ executed P4 (`status` active/archived, `mark_archived`/`prune`).

Remaining:
1. **ICS enrichment** — per-event `COLOR` + `VALARM` reminders for upcoming events (plan P5).
2. **More Layer-2/3 sources** — Brookings / ITIF / CNAS / Atlantic Council scrapers + more
   university feeds; each a bespoke adapter with its own access strategy (plan P2).
3. **Live ops (no new code)** — enable the SMTP emailer (`SMTP_*` env) and Postgres
   (`DATABASE_URL`); both code-complete + fallback-tested, just need creds/a server (plan P6).
