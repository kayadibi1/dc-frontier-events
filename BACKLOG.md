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

- ~~ICS enrichment~~ ✅ executed P5 (per-event `COLOR` + 1-day `VALARM` on upcoming).

Remaining:
1. **More Layer-2/3 sources** — bespoke per-site adapters. Per-source findings (probed 2026-05-30,
   no usable source shippable yet — each attempted adapter was BACKED OUT rather than ship unverified):
   - **Brookings** (`/events/`, httpx, dc_curated): MOST PROMISING. `article` cards, real titles,
     dates present ("June 10 2026", slugs are `ev-...`), 1 genuine upcoming AI event
     ("AI and economic mobility", 2026-06-10). Adapter built + reverted: produced a `json=108`/`ics=107`
     mismatch tied to a duplicated "social media" card, and the session's output channel was too flaky
     to verify cleanly. RETRY under a stable shell: handle the duplicate-card DOM + resolve the
     emit-count parity before committing.
   - **Hudson** (`/events`, curl_cffi): listing cards have truncated link text ("Learn More"), and
     the CURRENT listing is all geopolitics/energy — 0 AI/chip events. Detail pages have real
     titles+dates but fetching all 22 for 0 yield isn't worth it. Revisit only if Hudson schedules AI events.
   - **CNAS** (`/events`): 19 links but listing uses non-`article` cards (parsed 0 on saved fixture).
   - Probed-dead: ITIF (2 links), Atlantic Council (0 event links), RAND (sub-site links);
     university iCal UMD/Georgetown/Howard/American/VT/UMBC (404/403/0/DNS/SSL).
   LESSON: these HTML listings don't have clean 1-article→1-title→1-link→1-date structure, so a
   hand-written fixture test gives false confidence. Verify any new adapter against a SAVED REAL
   fixture (dev-parse for ≥1 on-topic kept event) AND a live run before committing.
2. **Live ops (no new code)** — enable the SMTP emailer (`SMTP_*` env) and Postgres
   (`DATABASE_URL`); both code-complete + fallback-tested, just need creds/a server (plan P6).
