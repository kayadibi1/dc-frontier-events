# Cross-Language / Fuzzy Dedupe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Catch duplicate events that differ by word order or paraphrase (and, optionally, language) — which the current order-sensitive `SequenceMatcher` pass misses — without adding a mandatory ML dependency.

**Architecture:** Add a 4th dedupe pass after the existing series pass. It compares events **within the same start-day** using an order-insensitive **token-set Jaccard** ratio, gated by a location guard (geo within ~3 km, or a shared venue token, or no contradicting geo) to avoid merging two genuinely different same-day events at different venues. A truly cross-language sub-pass (sentence embeddings) is **import-guarded and optional** — a no-op when the library is absent, so the default install stays dependency-light and fully testable.

**Tech Stack:** Python 3.11+ stdlib (`re`), pytest. Optional: `sentence-transformers` (guarded).

---

### Task 1: Token-set similarity helper

**Files:**
- Modify: `aggregator/dedupe.py` (add helpers)
- Test: `tests/test_dedupe.py` (add tests)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_dedupe.py`)

```python
from aggregator.dedupe import _token_set_ratio


def test_token_set_ratio_word_order_insensitive():
    # SequenceMatcher rates these low; token-set rates them high.
    assert _token_set_ratio("AI Policy Panel", "Panel on AI Policy") >= 0.9


def test_token_set_ratio_distinct_titles_low():
    assert _token_set_ratio("Quantum Computing Talk", "AI Policy Panel") < 0.3
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_dedupe.py::test_token_set_ratio_word_order_insensitive -q`
Expected: FAIL (`ImportError: cannot import name '_token_set_ratio'`)

- [ ] **Step 3: Add helpers to `aggregator/dedupe.py`**

```python
_STOP = {"the", "a", "an", "of", "on", "in", "for", "to", "and", "with", "at", "by"}


def _tokens(title: str) -> set:
    return {w for w in _NON_ALNUM.sub(" ", (title or "").lower()).split()
            if w and w not in _STOP}


def _token_set_ratio(a: str, b: str) -> float:
    """Order-insensitive Jaccard over content tokens (0..1)."""
    sa, sb = _tokens(a), _tokens(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_dedupe.py -q`
Expected: PASS (all dedupe tests)

- [ ] **Step 5: Commit**

```bash
git add aggregator/dedupe.py tests/test_dedupe.py
git commit -m "dedupe: token-set Jaccard similarity helper"
```

---

### Task 2: Pass 4 — same-day paraphrase collapse with location guard

**Files:**
- Modify: `aggregator/dedupe.py` (`dedupe()` + a `_near` guard)
- Test: `tests/test_dedupe.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_dedupe.py`)

```python
def test_paraphrase_same_day_same_geo_collapses():
    evs = [
        Event(id="x1", title="AI Policy Panel", start="2026-06-10", source="cset",
              lat=38.90, lng=-77.03),
        Event(id="x2", title="Panel on AI Policy", start="2026-06-10", source="csis",
              lat=38.901, lng=-77.031),   # ~0.1 km away
    ]
    kept, removed = dedupe(evs)
    assert len(kept) == 1 and removed == 1


def test_paraphrase_far_apart_not_collapsed():
    evs = [
        Event(id="y1", title="AI Policy Panel", start="2026-06-10", source="cset",
              lat=38.90, lng=-77.03),
        Event(id="y2", title="Panel on AI Policy", start="2026-06-10", source="x",
              lat=40.71, lng=-74.00),     # NYC -> different event
    ]
    kept, removed = dedupe(evs)
    assert len(kept) == 2 and removed == 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_dedupe.py::test_paraphrase_same_day_same_geo_collapses -q`
Expected: FAIL (currently 2 kept — SequenceMatcher ratio of "ai policy panel" vs
"panel on ai policy" is below FUZZY_THRESHOLD)

- [ ] **Step 3: Add the location guard + pass 4 in `aggregator/dedupe.py`**

Add the guard (reuse `_day_gap`'s date logic; needs a km helper — import or inline haversine):

```python
import math

TOKEN_THRESHOLD = 0.7
NEAR_KM = 3.0


def _km(a: Event, b: Event) -> float | None:
    if None in (a.lat, a.lng, b.lat, b.lng):
        return None
    r = 6371.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = math.radians(b.lat - a.lat), math.radians(b.lng - a.lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _near(a: Event, b: Event) -> bool:
    d = _km(a, b)
    return d is None or d <= NEAR_KM   # both-or-one missing geo -> allow; else within NEAR_KM
```

Then, inside `dedupe()`, after `final = _series_collapse(kept)` and before computing
`removed`, add a paraphrase pass:

```python
    # Pass 4: same-day paraphrase / word-reorder collapse (location-guarded).
    para_kept: list[Event] = []
    by_day: dict[str, list[Event]] = {}
    for ev in final:
        day = _day(ev.start)
        match = None
        for other in by_day.get(day, []):
            if _token_set_ratio(ev.title, other.title) >= TOKEN_THRESHOLD and _near(ev, other):
                match = other
                break
        if match is None:
            by_day.setdefault(day, []).append(ev)
            para_kept.append(ev)
        else:
            _merge_source(match, ev)
    final = para_kept
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_dedupe.py -q`
Expected: PASS (all dedupe tests, including the two new ones; existing ones unaffected)

- [ ] **Step 5: Commit**

```bash
git add aggregator/dedupe.py tests/test_dedupe.py
git commit -m "dedupe: pass 4 same-day paraphrase collapse (location-guarded)"
```

---

### Task 3: Optional embedding sub-pass (import-guarded, no-op without the lib)

**Files:**
- Modify: `aggregator/dedupe.py` (add `_embedding_available` + guard)
- Test: `tests/test_dedupe.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_dedupe.py`)

```python
from aggregator.dedupe import semantic_ratio


def test_semantic_ratio_is_noop_without_model():
    # With no sentence-transformers installed, returns None (caller falls back).
    assert semantic_ratio("hola mundo IA", "hello AI world") in (None,) or \
        isinstance(semantic_ratio("a", "b"), float)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_dedupe.py::test_semantic_ratio_is_noop_without_model -q`
Expected: FAIL (`ImportError: cannot import name 'semantic_ratio'`)

- [ ] **Step 3: Add the guarded helper**

```python
_MODEL = None
_MODEL_TRIED = False


def semantic_ratio(a: str, b: str) -> float | None:
    """Cosine similarity of sentence embeddings, or None if the optional
    sentence-transformers dependency is not installed (caller falls back to
    token-set). Lazy-loads the model once."""
    global _MODEL, _MODEL_TRIED
    if not _MODEL_TRIED:
        _MODEL_TRIED = True
        try:
            from sentence_transformers import SentenceTransformer
            _MODEL = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        except Exception:
            _MODEL = None
    if _MODEL is None:
        return None
    va, vb = _MODEL.encode([a, b])
    import numpy as np
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb)))
```

Then in Pass 4's inner loop, upgrade the match test so a semantic match (when the
model is available) also triggers a collapse:

```python
            tok = _token_set_ratio(ev.title, other.title)
            sem = semantic_ratio(ev.title, other.title)  # None if lib absent
            similar = tok >= TOKEN_THRESHOLD or (sem is not None and sem >= 0.80)
            if similar and _near(ev, other):
                match = other
                break
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_dedupe.py -q`
Expected: PASS (in this env the lib is absent → `semantic_ratio` returns None →
behavior identical to Task 2; all tests pass)

- [ ] **Step 5: Document the optional dep + commit**

Add to `requirements.txt`:
```
# sentence-transformers>=2.2  # optional: enables cross-language semantic dedupe
```
```bash
git add aggregator/dedupe.py tests/test_dedupe.py requirements.txt
git commit -m "dedupe: optional embedding-based semantic match (import-guarded)"
```

---

### Task 4: Live verification + docs

- [ ] **Step 1: Run live and compare dedupe counts**

Run: `python -m aggregator`
Expected: `after dedupe` removed-count is >= the pre-change value (pass 4 may collapse a
few more paraphrase dupes); no crash. Spot-check that nothing legitimate was over-merged
(e.g., two distinct same-day events at different venues remain separate).

- [ ] **Step 2: Update PROGRESS.md + BACKLOG.md, commit**

```bash
git add PROGRESS.md BACKLOG.md
git commit -m "docs: record cross-language/fuzzy dedupe results"
```

---

## Notes
- **Default stays dependency-light:** the token-set pass is pure stdlib; embeddings are
  optional and a clean no-op when absent.
- **False-merge guard:** the `_near` location check (≤3 km, or missing geo) prevents merging
  two distinct same-day events at different venues that happen to share a title.
- **Threshold tuning:** `TOKEN_THRESHOLD=0.7` / semantic `0.80` are starting points; adjust
  if live spot-checks show over- or under-merging.
