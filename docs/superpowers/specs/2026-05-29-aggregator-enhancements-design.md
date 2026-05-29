# Design — dc-frontier-events enhancement portfolio

**Date:** 2026-05-29 · **Mode:** brainstormed portfolio, executed autonomously (user pre-authorized).
**Baseline:** iteration 12 (`98b4658`) — 3 layers, 6 live sources, dedupe/filter/rank/big-names,
ICS+RSS+JSON+map+digest+alerts, CLI+README, 49 tests.

Each item is an independent, verifiable increment (one commit each), built against real live data.
Externally-dependent items ship a **dry-run / fallback** path so they're verifiable without creds/infra.

---

## 1. Multi-day series dedupe (quality)
**Problem:** GWU lists a multi-day event (e.g. "AI+EXPO 2026") as one entry per day → triplicate
feed/digest/alert rows.
**Design:** add a third dedupe pass after exact-UID + fuzzy-title-within-day. Group candidates by
`(source, normalized-title)` where entries are on **consecutive/near days (gap ≤ 2)** AND share the
same `source_url` (or id-base). Collapse to one event: `start` = earliest, `end` = latest, record
`raw["days"]`. Recurring meetups (same title, ~7-day gaps, distinct URLs) must **not** collapse.
**Success:** unit tests — (a) 3 consecutive same-URL entries → 1 with a date range; (b) weekly
same-title 7-day-apart entries → stay separate. Live: AI+EXPO 3 → 1; logged dedupe count rises.

## 2. Interactive map UX (presentation)
**Problem:** `map.html` is static pins only.
**Design:** embed the full kept set (geo + non-geo). Add Leaflet + MarkerCluster (CDN). Controls:
checkboxes for layer (1/2/3) + "big names only" + "upcoming only", a text search, a legend, and a
scrollable sidebar list synced to the map (click list → pan + open popup; filters update both).
Self-contained HTML.
**Success:** `map.html` parses (selectolax); contains the filter controls, search input, and a
sidebar list; embedded `EVENTS` length == kept count; geo-pin rendering preserved.

## 3. HTML digest (presentation)
**Design:** `digest.render_html(events, today)` → standalone inline-CSS HTML: header with counts,
big-names section, ranked upcoming list (date/title/source/topics/score/link). Pipeline writes
`out/digest.html` alongside `digest.md`. Reuses ranking + the digest's data selection.
**Success:** `digest.html` parses; contains the ranked event titles + a big-names section; unit test.

## 4. Pluggable notifier / emailer (delivery)
**Design:** `aggregator/notify.py` — `build_message(digest_html, alerts_md, today)` → an
`email.message.EmailMessage` (Subject includes upcoming + new-big-name counts; HTML body = digest
HTML; plain-text alt). Transport: if `SMTP_HOST`/`SMTP_USER`/`SMTP_PASS`/`SMTP_TO` env present →
send via `smtplib.SMTP`; else **dry-run** → write `out/email/digest-<today>.eml`. Pipeline calls it
(dry-run default). No new dependency (stdlib `email`/`smtplib`).
**Success:** dry-run writes a valid `.eml` (re-parsed by `email.parser`: has Subject + HTML part with
ranked content); unit tests for `build_message` and the dry-run transport. SMTP path is code-complete,
exercised only when env creds are set (documented).

## 5. Postgres backend + fallback (infra)
**Design:** `storage.PostgresStore` mirroring `Store` (psycopg 3): same DDL (Postgres types),
`upsert_many` (INSERT … ON CONFLICT (id) DO UPDATE), `all_events`, `existing_ids`, `count`, `close`.
`open_store()`: if `DATABASE_URL` set AND `psycopg` importable AND `connect()` succeeds →
`PostgresStore`; else log the reason and use SQLite. `psycopg[binary]` added to requirements as an
optional extra (commented).
**Success:** unit tests for `open_store` selection — no `DATABASE_URL` → sqlite; `DATABASE_URL` set
but driver missing or connect fails → sqlite fallback (logged), never raises. SQLite remains the
verified default; live Postgres documented as needing a reachable DB.
**Risk:** live Postgres path unverifiable here → mitigated by testing the selection/fallback and
keeping SQLite authoritative; `PostgresStore` SQL reviewed for parity.

## 6. Archive feed + last_seen tracking (infra/feature)
**Design:** add `first_seen`/`last_seen` columns (safe `ALTER TABLE … ADD COLUMN` guarded by a
pragma check). `upsert_many` sets `last_seen=now` (and `first_seen` on insert). Pipeline computes
`gone` = stored ids not in this run's kept (info only), logs "N events no longer listed". Emit
`events-archive.ics` from `store.all_events()` (the durable archive, incl. past).
**Success:** migration is idempotent on an existing db; unit tests for last_seen update + gone
detection; `events-archive.ics` parses, VEVENT count == store count.

## 7. More Luma sources (coverage) — best-effort, no faking
**Design:** probe additional candidate DC AI/tech Luma slugs (resolve slug → `cal-id`, fetch ICS,
confirm VEVENTs). Add only those that return a live feed; classify dc_curated per inspection.
**Success:** ≥1 new source live with kept events, verified end-to-end. If none resolve, record the
attempt honestly (no fake source) and skip.

---

## Execution order
1 → 2 → 3 → 4 → 5 → 6 → 7. Quality + presentation first (low risk, high visible value), then
delivery, then infra, then coverage. Each: implement → test (write tests first where it fits) →
live run → verify gates → update PROGRESS.md/BACKLOG.md → commit.

## Non-goals / preserved invariants
- No fake data; empty/failed sources stay quarantined-and-logged.
- Existing feeds (events.ics/feed.xml/upcoming/top/big-names/json/map/digest/alerts) keep working;
  all additions are additive.
- Offline, deterministic unit tests (no network in tests).
