# More Layer-2 / Layer-3 Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Broaden coverage with more think-tank (Brookings/ITIF/CNAS/Atlantic Council) and university feeds, using the existing adapter architecture.

**Architecture:** Two paths. (A) Any iCal feed is **config-only** — add a `Source(kind="ics", url=...)`; no code. (B) An HTML think-tank is a new `fetchers/<name>.py` modeled exactly on `aggregator/fetchers/csis.py` (httpx or curl_cffi + selectolax + a separable `parse_<name>_listing` with an offline fixture test). Because third-party DOMs are unknown ahead of time, each HTML source begins with a **probe task** that captures the real markup; the implementation task then uses the selectors that probe revealed.

**Tech Stack:** Python 3.11+, httpx, curl_cffi, selectolax, pytest.

---

### Task 1: Add any working iCal feed (config-only path)

**Files:**
- Modify: `aggregator/config.py` (append to `UNIVERSITY_SOURCES` or `LUMA_SOURCES`)

- [ ] **Step 1: Probe a candidate feed for live events**

Run (example — UMD; substitute any campus/Meetup iCal URL):
```bash
curl -sL -A "Mozilla/5.0" --max-time 25 "https://calendar.umd.edu/calendar.ics" | grep -c "BEGIN:VEVENT"
```
Expected: a number > 0 means the feed is live and parseable. If `0` or non-200, this
feed is not usable as a bare iCal — skip it (do NOT add a dead/empty source).

- [ ] **Step 2: Add the source (only if Step 1 returned > 0)**

In `aggregator/config.py`, append to `UNIVERSITY_SOURCES`:
```python
    Source("umd", "University of Maryland", "ics", 3, True,
           url="https://calendar.umd.edu/calendar.ics"),
```
(Set `dc_curated=True` for DC-area institutions; the GEO-authoritative filter still
drops any stray non-DC in-person events.)

- [ ] **Step 3: Run the pipeline and confirm the source contributes**

Run: `python -m aggregator`
Expected: a `[fetch] umd (layer 3): N events` line with N > 0, and `layers live` includes 3.

- [ ] **Step 4: Confirm feeds still parse, then commit**

Run: `python -m pytest tests/ -q` (Expected: PASS — config-only change)
```bash
git add aggregator/config.py
git commit -m "sources: add UMD Localist iCal (Layer 3)"
```

---

### Task 2: Probe a think-tank's events page (captures real markup)

**Files:**
- Create: `tests/fixtures/<name>_listing.html` (saved real markup for the offline test)

- [ ] **Step 1: Confirm access (httpx vs WAF) and capture the listing**

Run (example — Brookings):
```bash
python - <<'PY'
import httpx
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
r=httpx.get("https://www.brookings.edu/events/",headers=UA,follow_redirects=True,timeout=30)
print("status",r.status_code,"bytes",len(r.text))
open("tests/fixtures/brookings_listing.html","w",encoding="utf-8").write(r.text)
PY
```
Expected: `status 200` and a non-trivial byte count. If 403, repeat using
`curl_cffi.requests.Session(impersonate="chrome")` instead (as `cset.py` does).
If still blocked, abandon this source and pick another.

- [ ] **Step 2: Identify the event card selector, title, date, and link**

Run:
```bash
python - <<'PY'
import re
from selectolax.parser import HTMLParser
h=open("tests/fixtures/brookings_listing.html",encoding="utf-8").read()
t=HTMLParser(h)
# event detail links
from collections import Counter
c=Counter(re.sub(r"/[^/]+$","/<slug>",a.attributes.get("href","")) for a in t.css("a") if "/events/" in (a.attributes.get("href") or ""))
print("link shapes:", c.most_common(5))
# candidate card containers
for sel in ["article","[class*=event]","[class*=card]","li[class*=event]"]:
    n=t.css(sel)
    if n: print(sel, len(n), "| sample:", re.sub(r"\s+"," ",n[0].text(separator=" ")).strip()[:140]); break
PY
```
Record the working `card_selector`, the title element, the date text pattern, and the
link attribute from the output. These concrete values feed Task 3.

- [ ] **Step 3: Commit the fixture**

```bash
git add tests/fixtures/brookings_listing.html
git commit -m "sources: capture Brookings listing fixture for offline test"
```

---

### Task 3: Implement the think-tank adapter (modeled on csis.py)

**Files:**
- Create: `aggregator/fetchers/<name>.py`
- Modify: `aggregator/fetchers/__init__.py` (register the adapter)
- Modify: `aggregator/config.py` (add the `Source`)
- Test: `tests/test_<name>.py`

- [ ] **Step 1: Write the failing offline test** using the fixture from Task 2

```python
# tests/test_brookings.py
from pathlib import Path
from aggregator.config import Source
from aggregator.fetchers.brookings import parse_brookings_listing

SRC = Source("brookings", "Brookings", "brookings", 2, True,
             url="https://www.brookings.edu/events/")
HTML = Path("tests/fixtures/brookings_listing.html").read_text(encoding="utf-8")


def test_parses_events_with_dates_and_urls():
    events = parse_brookings_listing(SRC, HTML)
    assert len(events) >= 1
    e = events[0]
    assert e.title and e.start[:4].isdigit() and e.source == "brookings"
    assert e.source_url.startswith("http")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_brookings.py -q`
Expected: FAIL (`ModuleNotFoundError: aggregator.fetchers.brookings`)

- [ ] **Step 3: Implement the adapter** (copy `aggregator/fetchers/csis.py`, then adjust
the three site-specific values found in Task 2: the card selector, the title selector,
and the date regex). Skeleton with the parts to set marked:

```python
# aggregator/fetchers/brookings.py
from __future__ import annotations
import re
from datetime import datetime
import httpx
from selectolax.parser import HTMLParser
from ..config import Source
from ..models import Event
from ..normalize import detect_topics
from .base import SourceResult

BASE = "https://www.brookings.edu"
_DATE = re.compile(r"([A-Z][a-z]+ \d{1,2}, \d{4})")   # adjust if Task 2 showed another format
_WS = re.compile(r"\s+")
CARD_SELECTOR = "article"                              # <- set from Task 2 Step 2
TITLE_SELECTOR = "h3"                                  # <- set from Task 2 Step 2

def _clean(s): return _WS.sub(" ", s or "").strip()

def _date(text):
    m = _DATE.search(text or "")
    if not m: return None
    try: return datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()
    except ValueError: return None

def parse_brookings_listing(source: Source, html: str) -> list[Event]:
    tree = HTMLParser(html); out = []; seen = set()
    for card in tree.css(CARD_SELECTOR):
        a = card.css_first("a[href*='/events/']")
        if not a: continue
        href = (a.attributes.get("href") or "").split("?")[0]
        if "/events/" not in href: continue
        url = href if href.startswith("http") else BASE + href
        if url in seen: continue
        start = _date(_clean(card.text()))
        if not start: continue
        seen.add(url)
        h = card.css_first(TITLE_SELECTOR)
        title = _clean(h.text()) if h else _clean(a.text())
        if not title: continue
        out.append(Event(id=f"brookings-{href.rstrip('/').rsplit('/',1)[-1]}",
                         title=title, start=start, source=source.slug, source_url=url,
                         organizer="Brookings", topics=detect_topics(title)))
    return out

async def fetch_brookings(source: Source) -> SourceResult:
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    async with httpx.AsyncClient(headers={"User-Agent": ua}, timeout=30,
                                 follow_redirects=True) as c:
        r = await c.get(source.url)
        if r.status_code != 200:
            return SourceResult(source, [], r.status_code, f"HTTP {r.status_code}")
        return SourceResult(source, parse_brookings_listing(source, r.text), r.status_code, None)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_brookings.py -q`
Expected: PASS. (If it fails, the selectors from Task 2 need adjustment — fix
`CARD_SELECTOR`/`TITLE_SELECTOR`/`_DATE` and re-run.)

- [ ] **Step 5: Register the adapter + source**

In `aggregator/fetchers/__init__.py`: `from .brookings import fetch_brookings` and add
`"brookings": fetch_brookings` to `ADAPTERS`.
In `aggregator/config.py` `CSET_SOURCES`: `Source("brookings", "Brookings", "brookings", 2, True, url="https://www.brookings.edu/events/")`.

- [ ] **Step 6: Run full suite + live, then commit**

Run: `python -m pytest tests/ -q` (Expected: PASS)
Run: `python -m aggregator` (Expected: `[fetch] brookings (layer 2): N events`)
```bash
git add aggregator/fetchers/brookings.py aggregator/fetchers/__init__.py aggregator/config.py tests/test_brookings.py
git commit -m "sources: add Brookings Layer-2 adapter"
```

---

### Task 4: Repeat Task 2-3 per additional source; record outcomes

- [ ] For each of ITIF, CNAS, Atlantic Council: run the Task 2 probe; if accessible,
  do Task 3. If a site blocks all clients or has no parseable listing, record it in
  BACKLOG.md as "probed, not usable (reason)" — do not add a dead source.
- [ ] Update PROGRESS.md with the new live-source count and per-source kept counts; commit.

---

## Notes
- **No dead sources:** only add a `Source` after a probe shows live, parseable events.
- **Each adapter stays small** (one file, one `parse_*_listing` + `fetch_*`), mirroring
  `cset.py`/`csis.py`, so they're independently testable from a saved fixture.
- **GEO authority** in `filter.py` already protects against any non-DC in-person leakage,
  so `dc_curated=True` is safe for DC-area institutions.
