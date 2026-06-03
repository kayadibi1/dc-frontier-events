# Headless Render + Extract Sources — Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax. TDD throughout. Commit after each green task.

**Goal:** Add marquee-company + semiconductor event sources to the DC AI/chip radar via a reusable headless render→extract engine, so JS event pages are first-class and future JS sites are config, not code.

**Architecture:** `render.py` (Playwright headless Chromium, shared browser, bounded concurrency, never raises) → `extract.py` (layered: JSON-LD → `__NEXT_DATA__` → heuristic cards) → `fetchers/jsrender.py` (generic adapter, per-source hints in `config.JSRENDER_HINTS`) + `fetchers/watchlist.py` (hand-confirmed entries for feed-less orgs). All events pass the existing DC/topic/dedupe/validation/audit gates unchanged.

**Tech Stack:** Python 3.14, Playwright (async, Chromium), selectolax, existing `structured.py`/`normalize.py`/`models.py`.

---

### Task 0: Dependency + local browser

**Files:** Modify `requirements.txt`

- [ ] Add `playwright` to `requirements.txt`.
- [ ] `pip install playwright` then `python -m playwright install chromium` (local dev).
- [ ] Verify: `python -c "from playwright.async_api import async_playwright; print('ok')"` → `ok`.
- [ ] Commit: `chore(deps): add playwright for headless rendering`.

### Task 1: `render.py` — headless render helper (TDD)

**Files:** Create `aggregator/render.py`; Test `tests/test_render.py`

- [ ] **Test** (`tests/test_render.py`): render a `data:` HTML URL returns the markup; a bad scheme returns `""`; never raises.
```python
import asyncio
from aggregator.render import render, close_render

def test_render_returns_html_and_never_raises():
    html = asyncio.run(render("data:text/html,<h1 id=x>Hi</h1>", wait_for="#x"))
    assert "Hi" in html
    assert asyncio.run(render("http://nonexistent.invalid.localhost:1/")) == ""
    asyncio.run(close_render())
```
- [ ] Run → FAIL (no module).
- [ ] **Implement** `render(url, wait_for=None, timeout_ms=15000)`: lazy module-level shared `async_playwright().start()` + `chromium.launch(headless=True)`; `asyncio.Semaphore(3)`; `page.goto(url, wait_until="networkidle", timeout=timeout_ms)`; optional `page.wait_for_selector(wait_for, timeout=...)`; return `await page.content()`; wrap everything in try/except → `""`; `close_render()` closes browser+playwright if started.
- [ ] Run → PASS. Commit: `feat(render): headless Playwright render helper (bounded, never raises)`.

### Task 2: `extract.py` — layered extractor (TDD)

**Files:** Create `aggregator/extract.py`; Modify `aggregator/structured.py` (add `extract_all_events`); Test `tests/test_extract.py`

- [ ] **Test**: three synthetic HTML strings — (a) JSON-LD `Event`, (b) `__NEXT_DATA__` array of `{title,date,slug}`, (c) two `<article>` cards each with `<time datetime>` + `<a>` title — each yields ≥1 well-formed `Event` with correct `start` and `title`; topics come from the title.
```python
from aggregator.config import Source
from aggregator.extract import extract_events
SRC = Source("x","X","jsrender",2,False,url="https://x")
def test_jsonld_layer():
    html='<script type="application/ld+json">{"@type":"Event","name":"AI Summit","startDate":"2026-07-01T13:00:00Z","url":"https://x/e","location":{"@type":"Place","name":"DC"}}</script>'
    evs=extract_events(SRC, html, "2026-06-02")
    assert evs and evs[0].title=="AI Summit" and evs[0].start.startswith("2026-07-01")
```
- [ ] Run → FAIL.
- [ ] **Implement** `extract_events(source, html, today)`: try `_from_jsonld` (uses `structured.extract_all_events`), else `_from_nextdata` (regex `__NEXT_DATA__`, walk for event-shaped arrays — mirror `fetchers/itif.py`), else `_from_cards` (selectolax; per-source CSS from `config.JSRENDER_HINTS.get(source.slug,{})` or generic `article/li` + `time[datetime]` + heading + `a`). Each → `Event(id=f"{slug}-{n}"|slug, title, start, source, source_url, address/venue from location, topics=detect_topics(title))`. Add `structured.extract_all_events(html)->list[dict]` returning every JSON-LD Event (handle array/@graph/ItemList).
- [ ] Run → PASS. Commit: `feat(extract): layered JSON-LD/NEXT_DATA/cards event extractor`.

### Task 3: `fetchers/jsrender.py` — generic adapter (TDD)

**Files:** Create `aggregator/fetchers/jsrender.py`; Test `tests/test_jsrender.py`

- [ ] **Test**: inject a fake `render` returning fixture HTML → `fetch_jsrender` yields events; fake render returning `""` → `SourceResult.ok is False` (quarantine).
- [ ] Run → FAIL.
- [ ] **Implement** `fetch_jsrender(source)`: `html = await render(source.url, wait_for=JSRENDER_HINTS.get(source.slug,{}).get("wait_for"))`; if not html → `SourceResult(source,[],None,"render empty")`; else `SourceResult(source, extract_events(source,html,today), 200, None)`.
- [ ] Run → PASS. Commit: `feat(jsrender): generic headless adapter`.

### Task 4: `fetchers/watchlist.py` — curated marquee events (TDD)

**Files:** Create `aggregator/fetchers/watchlist.py`; Modify `aggregator/config.py` (add `WATCHLIST_EVENTS=[]`); Test `tests/test_watchlist.py`

- [ ] **Test**: a config of 3 entries (one future+live, one past, one dead-link via injected fetch) → only the future+live one survives, well-formed (`watchlist-` id, DC address, topics).
- [ ] Run → FAIL.
- [ ] **Implement** `fetch_watchlist(source, fetch=httpx_get)`: for each `WATCHLIST_EVENTS` entry: skip if `date[:10] < today`; GET `url` → skip if not 200; build `Event(id=f"watchlist-{slug(name)}", title=name, start=date, address=f"{venue}, Washington, DC", source_url=url, topics=detect_topics(name)+entry.get("topics",[]))`.
- [ ] Run → PASS. Commit: `feat(watchlist): curated, self-pruning marquee-event source`.

### Task 5: Recon — render candidates, save fixtures, decide per-source strategy

**Files:** `tools/recon_render.py` (throwaway)

- [ ] Write a recon script that, for each candidate URL (AI Expo, Nvidia, AWS, Microsoft, SIA, SEMI, CHIPS), `render()`s it, runs `extract_events`, and reports: #events, sample title+date+location, on-topic+DC counts, which layer fired. Save each rendered HTML to `tests/fixtures/<slug>_rendered.html`.
- [ ] Decide, per source: keep (real on-topic DC events) / move-to-watchlist (no page) / drop (blocked/empty). Record the confirmed `Source` rows + `JSRENDER_HINTS`.

### Task 6 (repeat per confirmed source): register + TDD + live-verify

For each source that passed Task 5:
- [ ] Add `tests/test_<slug>.py` asserting `extract_events` on its saved fixture yields the known real events.
- [ ] Add the `Source(kind="jsrender")` row to `config.CSET_SOURCES` (+ `JSRENDER_HINTS` entry, `SOURCE_HQ` if curated) and register nothing new in ADAPTERS (jsrender already there).
- [ ] `python tools/live_check.py <slug>` → real on-topic DC events. If 0 live → do NOT ship (BACKLOG rule); move to watchlist or drop.
- [ ] Commit per source: `feat(sources): add <name> via jsrender (verified live)`.

### Task 7: Register jsrender + watchlist kinds; full local build

**Files:** Modify `aggregator/fetchers/__init__.py` (ADAPTERS += jsrender, watchlist), `aggregator/config.py` (SOURCES)

- [ ] Add `"jsrender": fetch_jsrender, "watchlist": fetch_watchlist` to ADAPTERS.
- [ ] `python -m pytest -q` → all green.
- [ ] `python -m aggregator --out out --today <today>` → new sources appear; inspect kept events; `python tools/accuracy_check.py` ground-truths them.
- [ ] Commit.

### Task 8: Box infra + deploy + verify

- [ ] On box: `.venv/bin/pip install playwright && .venv/bin/python -m playwright install --with-deps chromium`.
- [ ] Deploy `aggregator/` + `tests/` + `requirements.txt` (tar→scp→extract→chown).
- [ ] `systemctl start dc-frontier-events.service` → BUILD success; confirm new sources live in `/var/www/events.emersus.ai/events.json`; run `--audit`.
- [ ] Push to GitHub; confirm CI green (note: CI runners need `playwright install chromium` in the workflow OR mark render tests `@pytest.mark.skipif(no browser)`).

### Task 9: Final correctness + accuracy verification

- [ ] Full suite green; `tools/accuracy_check.py` → all new events title+date verified vs their rendered source; live `--audit` 0 mismatch; integrity sweep 0 issues; both web pages still 100 Lighthouse.
- [ ] Update `MEMORY.md` ops note; final report.

## Self-review notes
- **Spec coverage:** render.py (Task 1), extract.py (Task 2), jsrender (Task 3), watchlist (Task 4), sources (5–6), accuracy/box/testing (7–9) — all spec sections covered.
- **Recon-gated sources:** per the spec's open question, exact URLs/strategies are confirmed in Task 5 before any source ships; CI browser caveat noted in Task 8.
- **Accuracy invariant:** no task bypasses the existing pipeline gates; Task 9 re-verifies.
