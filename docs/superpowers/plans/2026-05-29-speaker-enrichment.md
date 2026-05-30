# Speaker Enrichment (CSET + CSIS) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate `Event.speakers[]` from Layer-2 event detail pages and make `is_big_name` fire on speakers, so a "fireside with Jensen Huang" surfaces even when the listing card never names him.

**Architecture:** A new pure parser `enrich.extract_speakers(html)` handles both CSIS structured speaker nodes and CSET prose. An async `enrich.enrich_layer2(events, fetch)` fetches each Layer-2 event's detail page (curl_cffi for cset, httpx for csis) and sets `ev.speakers`. `filter._text_blob` is extended to include speakers. Wiring runs enrichment after fetch, before dedupe; it is best-effort (failures skip) and can be disabled with `--no-enrich`.

**Tech Stack:** Python 3.11+, selectolax, curl_cffi, httpx, pytest.

---

### Task 1: Speaker extraction parser

**Files:**
- Create: `aggregator/enrich.py`
- Test: `tests/test_enrich.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_enrich.py
from aggregator.enrich import extract_speakers

CSIS_HTML = """
<div class="event"><h1>Data Centers and AI</h1>
  <div class="speakers">
    <div class="speaker"><span class="speaker__name">Jensen Huang</span><span>NVIDIA</span></div>
    <div class="speaker"><span class="speaker__name">Gregory Allen</span><span>CSIS</span></div>
  </div></div>
"""

CSET_PROSE_HTML = """
<article><p>Please join CSET for a fireside chat featuring Dario Amodei and
Helen Toner, moderated by Jane Smith.</p></article>
"""


def test_extract_speakers_from_structured_nodes():
    names = extract_speakers(CSIS_HTML)
    assert "Jensen Huang" in names
    assert "Gregory Allen" in names


def test_extract_speakers_from_prose():
    names = extract_speakers(CSET_PROSE_HTML)
    assert "Dario Amodei" in names
    assert "Helen Toner" in names


def test_extract_speakers_dedupes_and_rejects_nonnames():
    html = '<div class="speaker">Register Now</div><div class="speaker">Sam Altman</div>'
    names = extract_speakers(html)
    assert "Sam Altman" in names
    assert "Register Now" not in names   # not a person name


def test_extract_speakers_empty_when_none():
    assert extract_speakers("<p>No speakers listed here.</p>") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_enrich.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'aggregator.enrich'`

- [ ] **Step 3: Write minimal implementation**

```python
# aggregator/enrich.py
"""Speaker enrichment for Layer-2 detail pages.

extract_speakers parses both structured speaker markup (CSIS:
[class*=speaker]/[class*=participant]) and prose ("featuring X and Y, moderated
by Z" -- CSET). enrich_layer2 fetches each Layer-2 event's detail page and sets
Event.speakers (best-effort; failures leave speakers empty).
"""

from __future__ import annotations

import re

from selectolax.parser import HTMLParser

from .config import Source
from .models import Event

# A person name: 2-4 capitalized words (allowing internal hyphen/period/').
_NAME = re.compile(r"\b([A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){1,3})\b")
# Words that look capitalized but are not names (cut false positives).
_STOP = {"Register Now", "Read More", "Learn More", "Add To", "Google Calendar",
         "Watch Now", "Event Page", "Privacy Policy", "United States"}
_INTRO = re.compile(r"(?:featuring|fireside chat with|joined by|with|moderated by|"
                    r"keynote by|in conversation with|speakers?:)\s+(.+?)(?:\.|\n|$)", re.I)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _looks_like_name(s: str) -> bool:
    s = s.strip()
    if s in _STOP or any(ch.isdigit() for ch in s):
        return False
    parts = s.split()
    return 2 <= len(parts) <= 4 and all(p[:1].isupper() for p in parts)


def extract_speakers(html: str) -> list[str]:
    tree = HTMLParser(html)
    found: list[str] = []

    # 1) structured nodes
    for node in tree.css("[class*='speaker'], [class*='participant'], [class*='panelist']"):
        name_node = node.css_first("[class*='name']") or node
        cand = _clean(name_node.text())
        if _looks_like_name(cand):
            found.append(cand)

    # 2) prose fallback ("featuring A and B, moderated by C")
    if not found:
        body = tree.body.text(separator=" ") if tree.body else (tree.text() or "")
        for m in _INTRO.finditer(body):
            chunk = m.group(1)
            for piece in re.split(r",|\band\b|&", chunk):
                for nm in _NAME.findall(piece):
                    if _looks_like_name(nm):
                        found.append(nm)

    # dedupe preserving order
    seen, out = set(), []
    for n in found:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_enrich.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add aggregator/enrich.py tests/test_enrich.py
git commit -m "enrich: speaker extraction parser (structured + prose)"
```

---

### Task 2: Include speakers in the big-name blob

**Files:**
- Modify: `aggregator/filter.py` (the `_text_blob` function)
- Test: `tests/test_filter.py` (add one test)

- [ ] **Step 1: Write the failing test** (append to `tests/test_filter.py`)

```python
def test_big_name_fires_on_speaker():
    ev = mk(title="Fireside chat", topics=["ai"], lat=38.9, lng=-77.03,
            speakers=["Jensen Huang"])
    kept, _ = apply_filters([ev])
    assert kept and kept[0].is_big_name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_filter.py::test_big_name_fires_on_speaker -q`
Expected: FAIL (is_big_name is False — speakers not in blob yet)

- [ ] **Step 3: Edit `_text_blob` to include speakers**

In `aggregator/filter.py`, change `_text_blob` to:

```python
def _text_blob(ev: Event) -> str:
    return " ".join([ev.title, ev.description, ev.address, ev.organizer,
                     " ".join(ev.speakers), ev.raw.get("location", "")])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_filter.py -q`
Expected: PASS (all filter tests, including the new one)

- [ ] **Step 5: Commit**

```bash
git add aggregator/filter.py tests/test_filter.py
git commit -m "filter: match big-name watchlist against speakers"
```

---

### Task 3: Async enrichment of Layer-2 events

**Files:**
- Modify: `aggregator/enrich.py` (add `enrich_layer2`)
- Test: `tests/test_enrich.py` (add async test with a fake fetcher)

- [ ] **Step 1: Write the failing test** (append to `tests/test_enrich.py`)

```python
import asyncio
from aggregator.config import Source
from aggregator.models import Event
from aggregator.enrich import enrich_layer2


def test_enrich_layer2_sets_speakers():
    events = [
        Event(id="csis-1", title="AI Talk", start="2026-06-01", source="csis",
              source_url="https://www.csis.org/events/ai-talk"),
        Event(id="dc2-1", title="Meetup", start="2026-06-01", source="DC2"),  # L1: skipped
    ]
    layer = {"csis": 2, "DC2": 1}

    async def fake_fetch(url, kind):
        return '<div class="speaker"><span class="name">Sam Altman</span></div>'

    asyncio.run(enrich_layer2(events, layer, fake_fetch))
    assert events[0].speakers == ["Sam Altman"]
    assert events[1].speakers == []          # Layer-1 event untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_enrich.py::test_enrich_layer2_sets_speakers -q`
Expected: FAIL with `ImportError: cannot import name 'enrich_layer2'`

- [ ] **Step 3: Add `enrich_layer2` to `aggregator/enrich.py`**

```python
import asyncio


async def enrich_layer2(events: list[Event], layer_by_source: dict[str, int],
                        fetch) -> int:
    """For each Layer-2 event with a source_url, fetch its detail page via
    `fetch(url, source_kind)` and set ev.speakers. Best-effort: a failed fetch
    leaves speakers empty. `fetch` is async and returns HTML (or '' on failure).
    Returns the number of events enriched with >=1 speaker."""
    targets = [e for e in events
               if layer_by_source.get(e.source, 0) == 2 and e.source_url]

    async def one(ev: Event) -> int:
        try:
            html = await fetch(ev.source_url, ev.source)
        except Exception:
            return 0
        ev.speakers = extract_speakers(html or "")
        return 1 if ev.speakers else 0

    results = await asyncio.gather(*[one(e) for e in targets])
    return sum(results)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_enrich.py -q`
Expected: PASS (all enrich tests)

- [ ] **Step 5: Commit**

```bash
git add aggregator/enrich.py tests/test_enrich.py
git commit -m "enrich: async enrich_layer2 over detail pages"
```

---

### Task 4: Wire enrichment into the pipeline (real fetcher + --no-enrich)

**Files:**
- Modify: `aggregator/enrich.py` (add `default_fetch`)
- Modify: `aggregator/pipeline.py` (call enrichment after fetch, before dedupe)
- Modify: `aggregator/__main__.py` (add `--no-enrich` flag)

- [ ] **Step 1: Add `default_fetch` to `aggregator/enrich.py`**

```python
import httpx

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


async def default_fetch(url: str, source_kind: str) -> str:
    """Fetch a detail page: curl_cffi (browser TLS) for cset (WAF), httpx else."""
    if source_kind == "cset":
        def _go():
            from curl_cffi import requests as creq
            return creq.Session(impersonate="chrome").get(url, timeout=30).text
        return await asyncio.to_thread(_go)
    async with httpx.AsyncClient(headers={"User-Agent": _UA}, timeout=30,
                                 follow_redirects=True) as c:
        r = await c.get(url)
        return r.text if r.status_code == 200 else ""
```

- [ ] **Step 2: Call enrichment in `aggregator/pipeline.py`**

Add the import near the other `from .` imports:

```python
from .enrich import default_fetch, enrich_layer2
```

In `run(...)`, change the signature to accept `enrich: bool = True`:

```python
def run(out_dir: str = "out", db_path: str = "data/events.db",
        today: str | None = None, enrich: bool = True) -> dict:
```

Immediately after the fetch loop builds `raw_events` (before `dedupe(raw_events)`), insert:

```python
    if enrich:
        layer_by_source = {s.slug: s.layer for s in SOURCES}
        n_enriched = asyncio.run(enrich_layer2(raw_events, layer_by_source, default_fetch))
        print(f"[enrich] speakers added to {n_enriched} Layer-2 events")
```

- [ ] **Step 3: Add `--no-enrich` to `aggregator/__main__.py`**

Add to the argparser, then pass it through:

```python
    p.add_argument("--no-enrich", action="store_true",
                   help="skip Layer-2 detail-page speaker enrichment (faster, fewer requests)")
    args = p.parse_args()
    run(out_dir=args.out, db_path=args.db, today=args.today, enrich=not args.no_enrich)
```

- [ ] **Step 4: Verify the suite still passes (enrichment is off in tests via direct calls)**

Run: `python -m pytest tests/ -q`
Expected: PASS (all tests; pipeline tests unaffected — none call `run` with network)

- [ ] **Step 5: Commit**

```bash
git add aggregator/enrich.py aggregator/pipeline.py aggregator/__main__.py
git commit -m "enrich: wire Layer-2 speaker enrichment into pipeline (--no-enrich to skip)"
```

---

### Task 5: Live verification

- [ ] **Step 1: Run the pipeline live**

Run: `python -m aggregator`
Expected: a line `[enrich] speakers added to N Layer-2 events` (N may be 0 if current
detail pages list no parseable speakers — that is honest, not a failure).

- [ ] **Step 2: Inspect enriched speakers + any new big-names**

Run:
```bash
python -c "import json;d=json.load(open('out/events.json',encoding='utf-8'));print([(e['title'][:40],e['speakers']) for e in d if e['speakers']][:10])"
```
Expected: any populated `speakers` are real person names; confirm any newly-flagged
big-name events genuinely name a watchlisted person (no false positives).

- [ ] **Step 3: Update PROGRESS.md + BACKLOG.md and commit**

Record the enriched count + any new big-names; mark the backlog item done.

```bash
git add PROGRESS.md BACKLOG.md
git commit -m "docs: record speaker-enrichment results"
```

---

## Notes
- **Best-effort, honest:** enrichment adds ~10-25 detail-page fetches per run; if a page
  blocks or lists no speakers, the event keeps empty `speakers` (never faked).
- **Precision:** `_looks_like_name` + `_STOP` guard against "Register Now"-style false names;
  the big-name watchlist (precision-tested in iteration 10) is the second gate.
- **Performance:** `--no-enrich` keeps the fast path for frequent runs.
