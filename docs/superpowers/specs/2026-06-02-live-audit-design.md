# Live Event Audit — design (sub-project 4)

**Date:** 2026-06-02
**Status:** Design — revised after Codex review; ready to plan against
**Depends on:** accuracy core + provenance labeling (both merged).

## Goal

The static layers make values correct *at parse time* and catch gross errors, but
they can't tell whether a stored value is still *actually* right — a venue that moved,
a date rescheduled, a title changed. This is rung 5 of the confidence ladder: a
**scheduled live ground-truth audit** that re-fetches each event's own source page and
diffs it against what we stored, surfacing mismatches for a human. It changes nothing
in the feeds; it only *reports*. Mirrors the credentials `--verify` mode for events.

## Scope

- Audit upcoming active events **only from the think-tank HTML sources** —
  `AUDIT_SOURCES = {cset, csis, brookings, cnas, atlanticcouncil}` — where a real
  detail page + structured data make a diff meaningful. Luma/GWU events come from
  authoritative iCal feeds and are **not** audited (re-fetching their pages is low
  value and would waste the cap on `unverifiable` noise). (Codex #3.)
- Bound by `AUDIT_MAX` = `int(os.environ.get("AUDIT_MAX", "60"))`; filter
  eligible∩upcoming∩has-`source_url` *before* applying the cap, and **log eligible vs
  audited** counts (no silent truncation).
- Fields diffed: **date**, **title**, and a **location note** (stored HQ fallback but
  the live page now exposes a real venue).
- Read-only: opens the store, re-fetches pages, writes `out/audit.md`, prints a console
  summary. Skips the pipeline (like `--verify`). Honest verdicts: `🚫 unreadable`
  (never a false mismatch), `❔ unverifiable` (no extractable ground truth).

## Prerequisite: `structured.py` returns `name`

`extract_structured` currently returns start/end/location/speakers but **not** the
Event `name` (Codex #1). Add `out["name"]` from the JSON-LD Event node (`node.get("name")`),
with a test. The audit's title diff uses `structured["name"]`, falling back to the
`og:title` meta with common site suffixes stripped (e.g. ` | CSIS`, ` - Brookings`).

## Architecture

- **New `aggregator/audit.py`**:
  - `audit_events(events, fetch, today_iso) -> list[dict]` — async. For each event
    (already filtered to eligible+upcoming+source_url), wrap the fetch:
    ```
    try: html = await fetch(ev.source_url, ev.source)
    except Exception: html = ""
    ```
    `""`/exception → `status="unreadable"`, no field verdicts (Codex #4). Otherwise
    `status="read"` and diff:
    - **date**: parse stored `start` and live `extract_structured(html)["start"]`.
      If the live value is naive (CSIS) and the stored value is offset-aware, attach
      UTC to the live value and convert to the stored offset **before** taking the
      date, so a UTC date-rollover isn't a false mismatch (Codex #2). Verdict:
      `match` / `mismatch (<stored> → <live>)` / `unverifiable` (no live date).
    - **title**: normalized compare (casefold, collapse whitespace, drop punctuation)
      of stored title vs `structured["name"]` (fallback stripped `og:title`) →
      `match` / `mismatch` / `unverifiable`.
    - **location note**: if `prov_get(ev, "location") == "hq"` and the live page has a
      structured venue/address → `live venue available: <X>`.
    Returns `{id, source, title, status, date, title_verdict, location_note}`.
  - `render_audit_md(rows, today_iso) -> str` — markdown table + a summary count line
    (match / mismatch / unverifiable / unreadable). **Escape `|`** in any cell so a
    title/note can't break the table (Codex). Pure, testable.
  - `run_audit(today_iso=None, out_dir="out", db_path="data/events.db") -> dict` —
    reconfigure stdout to utf-8 (like `verify.run_verify`); open store; select
    `active_events()` that are upcoming (`emit.filter_upcoming`), in `AUDIT_SOURCES`,
    with a `source_url`; log eligible count; cap at `AUDIT_MAX`; run `audit_events`
    with `enrich.default_fetch`; write `out/audit.md`; print summary; return counts.
- **Edit `aggregator/__main__.py`**: add `--audit` short-circuit (like
  `--verify`/`--email`): `from .audit import run_audit; run_audit(today_iso=args.today,
  out_dir=args.out, db_path=args.db); return`.
- **Deploy**: `deploy/dc-frontier-events-audit.service` + `.timer` (weekly,
  `python -m aggregator --audit`); box install is manual (note in the file).

## Testing

`audit_events` takes an injected async `fetch` → fully offline/deterministic (Codex
confirmed).
- `extract_structured` returns `name` (new structured test).
- match: live structured start/name equal stored → `date=match`, `title=match`.
- date mismatch: differing live date → `mismatch (… → …)`.
- date no-false-mismatch: CSIS naive-UTC live vs offset-aware stored, same instant →
  `match` (tz-normalized).
- title: punctuation/case-only diff → `match`; genuinely different → `mismatch`;
  `og:title` with ` | CSIS` suffix stripped → `match`.
- unreadable: injected `fetch` returns `""` **and** a variant that raises → both
  `status=unreadable`, no field mismatches.
- unverifiable: live page has no Event/title → `unverifiable`.
- location note: stored `provenance.location=hq` + live structured venue → note set.
- `render_audit_md`: rows + summary counts; a title containing `|` is escaped.
- (CLI/`run_audit` follows the untested-glue pattern of `verify.run_verify`.)

## Risks & limits

- **Network:** one fetch per audited think-tank event, weekly, capped, best-effort;
  not in the hot pipeline path.
- **False mismatches:** the normalized title compare, tz-aware date compare, and
  `unverifiable`/`unreadable` verdicts keep noise down; the audit only *reports*.
- **Coverage:** think-tank HTML sources only; Luma/GWU (authoritative iCal) and
  archived/past events are out of scope by design.

## Success criteria

1. `python -m aggregator --audit` writes `out/audit.md` diffing upcoming think-tank
   events' stored date/title/location vs their live source pages, with honest verdicts.
2. The pipeline and feeds are untouched (read-only).
3. `extract_structured` returns `name`; `audit_events`/`render_audit_md` are covered by
   offline tests (injected fetch); full suite green.
4. A weekly systemd timer template is added under `deploy/`.
