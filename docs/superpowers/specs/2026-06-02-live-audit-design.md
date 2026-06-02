# Live Event Audit — design (sub-project 4)

**Date:** 2026-06-02
**Status:** Design — autonomous; pending Codex review
**Depends on:** accuracy core + provenance labeling (both merged).

## Goal

The static layers (structured extraction + validation) make values correct *at parse
time* and catch gross errors, but they can't tell whether a stored value is still
*actually* right — a venue that moved, a date that was rescheduled, a title that
changed. This is rung 5 of the confidence ladder: a **scheduled live ground-truth
audit** that re-fetches each event's own source page and diffs it against what we
stored, surfacing mismatches for a human to act on. It changes nothing in the feeds;
it only *reports*. This mirrors the existing credentials `--verify` mode (`verify.py`)
but for events.

## Scope

- Audit the **upcoming active events** from the store (the actionable subset a
  subscriber relies on), capped at `AUDIT_MAX` (default 60) to bound network use; if
  the cap truncates, **log it** (no silent truncation).
- Fields diffed: **date** (`start[:10]`), **title**, and a **location note** (when the
  stored value was an HQ fallback but the live page now exposes a real venue).
- Read-only: opens the store, re-fetches source pages, writes `out/audit.md`, prints a
  console summary. Skips the pipeline (like `--verify`).
- Honest verdicts: an unreadable page is `🚫 unreadable` (never a false mismatch); a
  page with no extractable ground truth for a field is `❔ unverifiable`.

## Architecture

- **New `aggregator/audit.py`**:
  - `audit_events(events, fetch, today_iso) -> list[dict]` — async; for each event
    with a `source_url`, fetch the detail page via `fetch(url, source_kind)` (injected;
    defaults to `enrich.default_fetch`, which handles WAF sources), extract ground
    truth, and diff. Returns one row per event:
    `{id, source, title, status, date, title_verdict, location_note}`.
    - `status`: `"read"` if HTML came back, else `"unreadable"`.
    - date diff: compare stored `start[:10]` to `extract_structured(html)["start"][:10]`
      → `match` / `mismatch (stored→live)` / `unverifiable` (no structured date).
    - title diff: stored title vs structured `name` (fallback: `og:title` meta) under a
      normalized compare (casefold, collapse whitespace/punctuation) →
      `match` / `mismatch` / `unverifiable`.
    - location note: if the stored event's `raw.provenance.location == "hq"` and the
      live page exposes a structured venue/address, note `live venue available: <X>`
      (actionable: we used a fallback but a real venue now exists).
  - `render_audit_md(rows, today_iso) -> str` — a markdown table + a summary line
    (counts of match / mismatch / unverifiable / unreadable). Pure, testable.
  - `run_audit(today_iso=None, out_dir="out", db_path="data/events.db") -> dict` —
    opens the store, selects upcoming active events (≤ `AUDIT_MAX`), runs
    `audit_events` with `default_fetch`, writes `out/audit.md`, prints a summary,
    returns counts. Reconfigures stdout to utf-8 (emoji-safe) like `verify.run_verify`.
- **Edit `aggregator/__main__.py`**: add `--audit` (skips the pipeline, like
  `--verify`/`--email`): `from .audit import run_audit; run_audit(today_iso=args.today,
  out_dir=args.out, db_path=args.db); return`.
- **Deploy**: add `deploy/dc-frontier-events-audit.service` + `.timer` (weekly,
  `python -m aggregator --audit`). The actual box install is manual (note in the file).

## Testing

`audit_events` takes an injected async `fetch`, so all tests are offline/deterministic.
- match: live page's structured start/title equal stored → `date=match`, `title=match`.
- date mismatch: live structured start differs → `date` reports `mismatch (… → …)`.
- title mismatch: differing normalized titles → `title_verdict=mismatch`; punctuation/
  case-only differences → `match`.
- unreadable: `fetch` returns `""` → `status=unreadable`, no false mismatch.
- unverifiable: live page has no `Event`/title → date/title `unverifiable`.
- location note: stored `provenance.location=hq` + live structured venue → note set.
- `render_audit_md`: table rows + a summary count line; emoji verdicts.
- (CLI/`run_audit` follows the untested-glue pattern of `verify.run_verify`; covered by
  the pure `audit_events`/`render_audit_md` tests, matching how `verify.py` is tested.)

## Risks & limits

- **Network cost:** one fetch per audited event, weekly, capped at `AUDIT_MAX`,
  best-effort (a failed fetch is `unreadable`, never blocks). Not run in the hot
  pipeline path.
- **False mismatches:** titles/dates legitimately differ in formatting; the normalized
  compare + `unverifiable`/`unreadable` verdicts keep noise down. The audit *reports*,
  it never mutates feeds — a human decides.
- **Coverage:** only upcoming active events with a `source_url`; past/archived events
  and feed-only events without detail pages aren't audited (by design).

## Success criteria

1. `python -m aggregator --audit` writes `out/audit.md` diffing upcoming events'
   stored date/title/location against their live source pages, with honest
   match/mismatch/unverifiable/unreadable verdicts.
2. The pipeline and feeds are untouched (read-only).
3. `audit_events`/`render_audit_md` are covered by offline tests; full suite green.
4. A weekly systemd timer template is added under `deploy/`.
