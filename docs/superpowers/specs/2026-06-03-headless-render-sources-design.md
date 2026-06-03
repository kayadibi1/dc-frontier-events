# Headless render + extract: marquee‑company & semiconductor event sources

**Status:** Design — approved 2026-06-03
**Author:** Claude (brainstormed with the operator)

## Goal

Add the two highest‑prestige, currently‑uncovered event categories to the DC AI/chip‑policy
radar:

1. **Marquee AI‑company events** — Nvidia (AI Summit DC), AWS Public Sector Summit, Microsoft
   DC, the **AI Expo for National Competitiveness** (SCSP), plus OpenAI "The Workshop" and
   Anthropic DC (which publish no feed at all).
2. **Semiconductor industry** — SIA, SEMI (public‑policy / DC), the CHIPS program.

These mostly lack clean feeds: the companies announce via **client‑side‑rendered (JS) event
pages** — or nothing — and the chip associations are JS SPAs. The existing `httpx`/`curl_cffi`
adapters can't see content injected by JavaScript. The deliverable is a **reusable headless
render → extract engine** so JS event pages become first‑class sources and *future* JS sites
are added by config, not new code, plus a tiny **curated watchlist** for orgs that publish
nothing.

**Non‑goal / accuracy invariant:** rendering only changes *how we obtain the HTML*. Every event
still passes the unchanged DC + topic + dedupe + two‑phase‑validation gates and the weekly
`--audit` / `tools/accuracy_check.py` ground‑truth. A render is never a license to fabricate.

## Architecture

Four cohesive units + config. The engine is built once; sources are then config.

```
gather_all ──> fetch_jsrender(source) ──> render(url)  [headless Chromium]
                                      └──> extract_events(source, html, today) ──> [Events]
           ──> fetch_watchlist(source) ─> verify links live ──────────────────> [Events]
                                                                                    │
                       (unchanged) normalize → validate_pre → dedupe → filter →────┘
                                   → geocode → validate_post → emit
```

### 1. `aggregator/render.py` — headless rendering

```python
async def render(url: str, wait_for: str | None = None, timeout_ms: int = 15000) -> str
async def close_render() -> None            # close the shared browser at pipeline end
```

- **Playwright** async API, a single **shared** headless Chromium per process (launched lazily,
  reused across sources — launching one browser per source is too costly).
- **Bounded concurrency:** an `asyncio.Semaphore(3)` caps simultaneous pages (≤ ~1 GB peak on
  the 8 GB box).
- Per page: `goto(url, wait_until="networkidle", timeout=timeout_ms)`; if `wait_for` (a CSS
  selector) is given, additionally `wait_for_selector`; then `content()`.
- **Never raises.** Any error/timeout → returns `""`. The caller quarantines the source
  (logged, never fabricated), exactly like every other adapter failure.
- Realistic UA + headers to reduce trivial bot blocks (no evasion beyond a normal browser).

### 2. `aggregator/extract.py` — layered event extraction (pure)

```python
def extract_events(source: Source, html: str, today_iso: str) -> list[Event]
```

Tried in order; first layer that yields events wins (most stable first):

1. **schema.org Event JSON‑LD** — collect *all* `Event` objects across `<script ld+json>` blocks
   (handle arrays / `@graph` / `ItemList`). Reuses/extends `structured.py` (which today returns a
   single event) with a multi‑event helper. Gives authoritative name/startDate/location/url.
2. **`__NEXT_DATA__` / embedded JSON** — find arrays of dicts that look like events (a title‑ish
   key + a date‑ish key), like the ITIF adapter already does.
3. **Heuristic cards** — a repeating block carrying a title + a date (`<time datetime>` or a
   parseable string) + a detail link, optionally guided by per‑source CSS hints.

Each produced `Event` gets `topics = detect_topics(title [+ description])`. **Location capture is
mandatory** for the global company pages (Nvidia/AWS/Microsoft list worldwide events; only the DC
ones must survive) — the extractor must surface venue/city so the DC filter can do its job.

Pure function → unit‑tested against saved rendered‑HTML fixtures, like every existing adapter.

### 3. `aggregator/fetchers/jsrender.py` — the generic adapter

```python
async def fetch_jsrender(source: Source) -> SourceResult
```

`html = await render(source.url, wait_for=hint)` → `extract_events(source, html, today)` →
`SourceResult` (quarantine on empty html). Per‑source tuning lives in a config map, **not** code:

```python
# config.py
JSRENDER_HINTS: dict[str, dict] = {
    # slug: {"wait_for": css, "strategy": "jsonld|nextdata|cards",
    #        "card": css, "title": css, "date": css, "link": css, "location": css}
}
```
The adapter reads `JSRENDER_HINTS.get(source.slug, {})`. A new JS site is a `Source(kind="jsrender")`
row + (optionally) a hints entry.

### 4. Curated watchlist — `aggregator/fetchers/watchlist.py`

For orgs that publish **no** events page (OpenAI/Anthropic): rendering can't conjure what isn't
posted, so a few hand‑confirmed entries fill the gap.

```python
# config.py
WATCHLIST_EVENTS: list[dict] = [
    {"name": ..., "date": "YYYY-MM-DD[THH:MM...]", "venue": ..., "url": ..., "topics": [...]},
]

async def fetch_watchlist(source: Source) -> SourceResult
```

For each entry: a lightweight `httpx` GET confirms the `url` is **live (200)**; build an `Event`
with the hand‑entered date/venue/topics. **Drop** entries whose date is past or whose link is dead
— so the watchlist self‑prunes and never shows stale/fabricated events. One source slug
(`watchlist`), Layer 2, `dc_curated=True` (entries are DC by construction).

## Sources (each validated live before it ships — BACKLOG rule)

| slug | kind | dc_curated | URL / note |
|---|---|---|---|
| `aiexpo` | jsrender | True | AI Expo for National Competitiveness (SCSP) — the marquee DC event |
| `nvidia` | jsrender | False | nvidia.com events → DC filter keeps AI Summit DC etc. |
| `awsps` | jsrender | False | AWS Public Sector Summit / events → DC filter |
| `microsoft` | jsrender | False | Microsoft DC events → DC filter |
| `sia` | jsrender | True | Semiconductor Industry Association events |
| `semi` | jsrender | False | SEMI public‑policy / DC events → DC filter |
| `chips` | jsrender | True | NIST CHIPS program events (chips.gov) |
| `watchlist` | watchlist | True | OpenAI "The Workshop", Anthropic DC (hand‑confirmed) |

Global company/association pages are **not** `dc_curated`: the extractor pulls all their events and
the existing DC geo/text filter keeps only DC‑metro ones. Any source that renders blocked/empty, or
yields no real on‑topic DC event live, is **not shipped** (quarantined or omitted) — never faked.

## Error handling & robustness

- `render` never raises → `""` → source quarantined (logged in the run summary, surfaced on the
  status page, regression‑detected by `health.py`).
- Per‑page timeout (15 s) + `Semaphore(3)` bound the build's added wall‑clock (~+30–60 s for ~7
  rendered sources) and memory.
- Watchlist drops past/dead entries every run.
- Anti‑bot: some sites (e.g. SCSP's REST is Shield‑blocked) may still refuse a headless browser; if
  so that source quarantines honestly — no evasion arms race.

## Box infrastructure (one‑time)

- `requirements.txt` += `playwright`.
- On the box: `.venv/bin/playwright install chromium` + `playwright install-deps chromium` (Chromium's
  shared libs on Ubuntu). ~300 MB. The 12 h systemd build is the only new runtime cost.
- No change to the dry‑run/email posture or the `Environment=` drop‑in pattern.

## Testing (TDD)

- **`extract.py`** — pure; one saved **real rendered‑HTML fixture** per source → unit tests
  (≥1 well‑formed event, correct date/location, on‑topic). The layered strategies each get a test.
- **`render.py`** — a live integration test (skipped when no browser is installed).
- **`watchlist`** — unit tests: config → Events; past‑dated and dead‑link entries dropped.
- **Live gate** — `tools/live_check.py <slug>` must show real on‑topic DC events for each source
  before it's added to `SOURCES`; `tools/accuracy_check.py` ground‑truths them post‑build.

## Out of scope (deferred, not rejected)

Gov/policy summits (govevents.com), federal‑agency events, academic CS‑department seminars, and
exec‑ed/fellowships — all viable later against this same engine, but not in this spec.

## Open question for the operator

The marquee company URLs (esp. OpenAI/Anthropic events pages, and the exact AI Expo / SIA / SEMI
events URLs) are assumed, not yet confirmed. The implementation plan's first task is a **recon pass**
that confirms each URL renders and exposes extractable events; any that don't are dropped or moved to
the watchlist. No source ships unverified.
