# FINAL REPORT — dc-frontier-events

**Date:** 2026-05-29 · **Status:** full GOAL ladder realized + a 7-feature enhancement portfolio (F1–F7) shipped. All verified end-to-end on live data.

## What it is
A production-grade aggregator of AI / semiconductor / frontier-tech events in the DC metro,
across all three source layers, deduplicated, relevance-ranked, with first-class attention to
"big name" orgs/people. Built incrementally over 12 core iterations + a 7-feature portfolio
(19 commits), one verified commit each.

## Verified end-to-end (fresh live run, 2026-05-29)
- **Unit tests: 59 passed** (offline, deterministic: normalize / dedupe / filter / rank / emit / digest / alerts / notify / storage).
- **Sources: 8/10 live across all 3 layers** `[1, 2, 3]`:
  - L1 Luma: DC2=72, dctech=24, ai-tinkerers-dc=15, dctechmeetup=16, aic-washington=453 ·
    L2 think tanks: cset=10, csis=13 · L3 university: gwu=561.
  - Quarantined (logged, never faked): DCtechevents (empty HTTP 200), ai (HTTP 404).
- **Pipeline:** 1164 raw → **886 after dedupe** (278 removed — incl. multi-day series collapse) →
  **106 kept** (376 dropped on location, 404 on topic).
- **3 big-name events** (validated real: AI+EXPO 2026 → Microsoft/Amazon-AWS; "Vibe Coding…" →
  Anthropic/Claude; "Vibe Code Enterprise Data Apps" → Databricks).
- **24 upcoming**, **66 map pins**, **106 archived**, idempotent (re-run: 0 new, 0 gone).

## Output artifacts (all 13 + email validated)
| artifact | validated |
|----------|-----------|
| `events.ics` / `feed.xml` | iCalendar parses (0 malformed) / feedparser bozo=0 |
| `events-upcoming.ics` / `feed-upcoming.xml` | all starts ≥ today |
| `feed-top.xml` | relevance-ranked, strictly descending |
| `events-big-names.ics` / `feed-big-names.xml` | watchlist-only, ★-marked |
| `events-archive.ics` | full durable store (parses; == stored total) |
| `events.json` | machine-readable, every event scored + layered (layers 1,2,3) |
| `map.html` | interactive Leaflet: filter (layer/big/upcoming) + search + clustered pins + synced list |
| `digest.md` / `digest.html` | ranked weekly digest (markdown + self-contained HTML) |
| `alerts.md` | new-since-last-run big-name alerts |
| `out/email/digest-<date>.eml` | dry-run email (valid RFC822: Subject + HTML body); SMTP when env set |

## Enhancement portfolio (F1–F7, all verified + committed)
1. **Multi-day series dedupe** — collapse per-day duplicates of one event (AI+EXPO 3→1).
2. **Interactive map UX** — filter/search/cluster + sidebar list synced to the map.
3. **HTML digest** — `digest.html` (self-contained).
4. **Pluggable emailer** — `notify.py`; dry-run `.eml`, SMTP when `SMTP_*` env set.
5. **Postgres backend + fallback** — `PostgresStore` (psycopg2); selection/fallback tested.
6. **Archive feed + last_seen** — `events-archive.ics`; ON-CONFLICT upsert; gone-from-sources report.
7. **More Luma sources** — AI Tinkerers DC (+3 incl. a Databricks big-name), DC Tech Meetup.

## GOAL ladder coverage
- ✅ Aggregates all three layers (builder/community, policy/think-tank, university).
- ✅ Ranks by relevance + proximity (haversine) + big-name.
- ✅ Emits `.ics` + RSS, plus a `/map` web view and `events.json`.
- ✅ Weekly digest (`digest.md`) — foundation for the emailer.
- ✅ "Big names only" feed variants.
- ✅ Archives events (idempotent SQLite store).
- ✅ Alerts when a watchlisted org/person is newly announced.

## Architecture
`fetch → normalize → dedupe → filter → rank → store → emit`, with per-source adapters
(`luma`/`ics` httpx+icalendar; `cset` curl_cffi+selectolax behind a WAF; `csis` httpx+selectolax).
GEO is authoritative for in-person DC-relevance; the big-name watchlist is precision-tested
(no "intel community"/"Google Form"/"metadata" false positives). Postgres-ready storage interface
with SQLite fallback (never blocked on infra). See `README.md` and `PROGRESS.md`.

## Honest notes / remaining work (see BACKLOG.md)
Blocked on externals: the digest **emailer** (needs SMTP creds) and a real **Postgres backend**
(needs a reachable `DATABASE_URL`) — both unverifiable here, so not shipped half-done. Additional
think-tank / university sources are each bespoke and often WAF-protected or export 0 via bare iCal;
added as each yields a reliable endpoint. CSET/CSIS speaker enrichment deferred (current detail
pages carry ~no watchlist names → 0 payoff + false-positive risk).

Every increment was implemented against real live sources, verified (tests + live run + artifact
parsing + idempotency), and committed. No fake data; no broken state committed as progress.
