# FINAL REPORT — dc-frontier-events

**Date:** 2026-05-29 · **Status:** the full GOAL "ambitious finished state" ladder is realized and verified end-to-end on live data.

## What it is
A production-grade aggregator of AI / semiconductor / frontier-tech events in the DC metro,
across all three source layers, deduplicated, relevance-ranked, with first-class attention to
"big name" orgs/people. Built incrementally over 12 verified iterations (one commit each).

## Verified end-to-end (fresh live run, 2026-05-29)
- **Unit tests: 49 passed** (offline, deterministic: normalize / dedupe / filter / rank / emit / digest / alerts / storage).
- **Sources: 6/8 live across all 3 layers** `[1, 2, 3]`:
  - L1 Luma: DC2=72, dctech=24, aic-washington=453 · L2: cset=10, csis=13 · L3: gwu=561.
  - Quarantined (logged, never faked): DCtechevents (empty HTTP 200), ai (HTTP 404).
- **Pipeline:** 1133 raw → **1027 after dedupe** (106 cross-listed dupes removed) → **109 kept**
  (366 dropped on location, 552 on topic).
- **4 big-name events** (validated real: AI+EXPO 2026 → Microsoft/Amazon-AWS; "Vibe Coding…" → Anthropic/Claude).
- **28 upcoming**, **69 map pins**, idempotent (re-run: 0 new, stored stable at 109).

## Output artifacts (all 11 validated)
| artifact | validated |
|----------|-----------|
| `events.ics` / `feed.xml` | iCalendar parses (0 malformed) / feedparser bozo=0 |
| `events-upcoming.ics` / `feed-upcoming.xml` | all starts ≥ today |
| `feed-top.xml` | relevance-ranked, strictly descending |
| `events-big-names.ics` / `feed-big-names.xml` | watchlist-only, ★-marked |
| `events.json` | machine-readable, every event scored + layered (layers 1,2,3 present) |
| `map.html` | self-contained Leaflet map, 69 GEO pins |
| `digest.md` | ranked weekly digest |
| `alerts.md` | new-since-last-run big-name alerts |

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
