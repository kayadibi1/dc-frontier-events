# Pro-Dark Apple Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle index, map, all emails, subscribe pages, and status page in Apple "Pro dark" per `docs/superpowers/specs/2026-06-09-pro-dark-redesign-design.md`. Zero functional change.

**Architecture:** Pure presentation work: replace CSS token values and a handful of HTML string templates in `web.py`, `digest.py`, `emit.py`, `subscribe_server.py`, `health.py`. DOM structure, class names, data-* attributes, JS, JSON-LD, email tables/headers all keep their shape — the existing 404-test suite is the structural safety net, plus 3 new value assertions (TDD) for decisions that matter functionally: dark color-scheme metas + bgcolor in email, dark tile provider in map, new hero tagline in index.

**Tech Stack:** No new dependencies. chrome-devtools MCP for Lighthouse + screenshots.

**Tokens (from spec):** canvas `#000000` · surface `#1d1d1f` · border `#424245` · text `#f5f5f7` · muted `#86868b` · muted-2 `#a1a1a6` · accent `#2997ff` · big `#ff453a` · green `#30d158` · amber `#ffd60a` · pills `980px` · cards 14–16px.

---

### Task 1: Index (`web.py`) — new tokens, hero, frosted controls, dark cards

**Files:**
- Modify: `tests/test_web.py` (append)
- Modify: `aggregator/web.py` (`_CARD_CSS` block; hero markup inside `render_index`)

- [ ] **Step 1: Append failing test to `tests/test_web.py`**

```python
def test_index_is_pro_dark():
    html = render_index(_EVENTS, TODAY)            # reuse the module's existing fixtures
    assert "AI events in DC." in html              # new hero tagline
    assert "linear-gradient(135deg" not in html    # gradient hero is gone
    assert "--bg:#000" in html                     # dark canvas token
```

(Adapt fixture/today names to what the existing tests in this file use.)

- [ ] **Step 2: Run it — expect FAIL on the tagline assertion**

Run: `python -m pytest tests/test_web.py -q` → 1 failed.

- [ ] **Step 3: Replace `_CARD_CSS` body with the dark token sheet**

Keep every selector/class name; replace values. New sheet (complete):

```css
*{box-sizing:border-box}
:root{--ink:#f5f5f7;--muted:#86868b;--muted2:#a1a1a6;--accent:#2997ff;
--bg:#000;--card:#1d1d1f;--line:#424245;--chip:#2c2c2e;--big:#ff453a}
body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
background:var(--bg);color:var(--ink);line-height:1.45}
a{color:var(--accent)}
.hero{background:#000;color:#f5f5f7;padding:52px 20px 34px}
.hero-in{max-width:920px;margin:0 auto}
.hero h1{font-size:40px;margin:0;letter-spacing:-.02em;font-weight:700;line-height:1.08}
.hero h1 .dim{color:var(--muted)}
.hero p{margin:10px 0 0;color:var(--muted2);font-size:15px;max-width:640px}
.stats{margin-top:18px;display:flex;gap:22px;flex-wrap:wrap;font-size:13px;color:var(--muted2)}
.stats b{font-size:19px;color:#fff;display:block;line-height:1;font-weight:700}
.cta{margin-top:22px;display:flex;gap:9px;flex-wrap:wrap}
.btn{display:inline-flex;align-items:center;gap:6px;background:var(--accent);color:#000;font-weight:600;
font-size:13.5px;text-decoration:none;padding:9px 16px;border-radius:980px;border:0;cursor:pointer}
.btn.ghost{background:var(--card);color:#f5f5f7;border:1px solid var(--line)}
.btn:hover{opacity:.88}
.wrap{max-width:920px;margin:0 auto;padding:18px 20px 60px}
.controls{position:sticky;top:0;background:rgba(0,0,0,.72);-webkit-backdrop-filter:blur(12px);
backdrop-filter:blur(12px);padding:14px 0 10px;z-index:5;border-bottom:1px solid var(--line)}
#q{width:100%;padding:11px 13px;border:1px solid var(--line);border-radius:12px;font-size:15px;
background:var(--card);color:var(--ink)}
#q::placeholder{color:var(--muted)}
.filters{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px;align-items:center}
.chip{border:1px solid var(--line);background:var(--card);color:var(--muted2);border-radius:980px;
padding:5px 12px;font-size:12.5px;cursor:pointer;user-select:none}
.chip.on{background:#f5f5f7;border-color:#f5f5f7;color:#1d1d1f}
.chip.topic.on{background:var(--accent);border-color:var(--accent);color:#000}
.chip:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
#q:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.sep{width:1px;height:20px;background:var(--line);margin:0 3px}
#count{color:var(--muted);font-size:12.5px;margin-top:9px}
.daygroup{margin-top:22px}
.dayhead{font-size:13px;font-weight:700;color:var(--muted);text-transform:uppercase;
letter-spacing:.06em;padding-bottom:7px;margin-bottom:8px}
.card{display:flex;gap:14px;padding:16px;border:1px solid var(--line);background:var(--card);
border-radius:16px;margin-bottom:10px}
.card:hover{border-color:#5a5a5e}
.when{flex:0 0 64px;text-align:center}
.when .d{font-size:22px;font-weight:700;line-height:1;color:#fff}
.when .mo{font-size:11px;font-weight:700;text-transform:uppercase;color:var(--accent)}
.when .t{font-size:11px;color:var(--muted);margin-top:3px}
.body{flex:1;min-width:0}
.title{font-size:16px;font-weight:650;margin:0 0 3px;text-decoration:none;color:var(--ink)}
.title:hover{text-decoration:underline}
.title .star{color:var(--big)}
.meta{font-size:12.5px;color:var(--muted);display:flex;gap:7px;flex-wrap:wrap;align-items:center}
.tag{background:var(--chip);color:var(--muted2);border-radius:980px;padding:2px 9px;font-size:11px;font-weight:600}
.badge{border-radius:980px;padding:2px 9px;font-size:11px;font-weight:700}
.b-virtual{background:rgba(41,151,255,.16);color:#6db4ff}.b-person{background:rgba(48,209,88,.16);color:#30d158}
.b-big{background:rgba(255,69,58,.16);color:#ff6961}
.src{font-size:11.5px;color:var(--muted)}
.addrow{margin-top:7px}
.addrow a{font-size:12px;color:var(--accent);text-decoration:none;font-weight:600}
.empty{padding:40px 0;text-align:center;color:var(--muted)}
footer{max-width:920px;margin:0 auto;padding:24px 20px 50px;color:var(--muted);font-size:12.5px;
border-top:1px solid var(--line)}
footer a{color:var(--muted2)}
.signup{background:var(--card);border:1px solid var(--line);border-radius:16px;
padding:15px 18px;margin:16px 0 2px}
.signup h2{margin:0 0 3px;font-size:15.5px}
.signup .sub{margin:0 0 10px;font-size:13px;color:var(--muted2)}
.signup form{display:flex;gap:8px;flex-wrap:wrap}
.signup input[type=email]{flex:1;min-width:220px;padding:10px 12px;border:1px solid var(--line);
border-radius:12px;font-size:15px;background:#2c2c2e;color:var(--ink)}
.signup button{background:var(--accent);color:#000;font-weight:600;border:0;border-radius:980px;
padding:10px 20px;font-size:14px;cursor:pointer}
.signup button:hover{opacity:.88}
.signup .hp{position:absolute;left:-9999px;width:1px;height:1px;opacity:0}
.spamnote{background:rgba(255,214,10,.1);border:1px solid rgba(255,214,10,.3);border-radius:12px;
padding:8px 10px;margin:10px 0 0;font-size:12px;color:#ffd60a;line-height:1.45}
@media(max-width:560px){.when{flex-basis:50px}.hero h1{font-size:28px}}
```

- [ ] **Step 4: Replace the hero block inside `render_index`'s returned f-string**

```html
<div class="hero"><div class="hero-in">
<h1>AI events in DC.<br><span class="dim">Tracked. Verified. Ranked.</span></h1>
<p>AI, semiconductor, and frontier-tech events across the DC metro —
think tanks, universities, and the builder community, deduplicated and ranked.</p>
<div class="stats"> …unchanged stats divs… </div>
<div class="cta"> …unchanged buttons… </div>
</div></div>
```

(Only the `<h1>`/`<p>` lines change; stats/cta markup stays byte-identical. The
`<title>`, meta description, og: tags, JSON-LD are untouched.)

- [ ] **Step 5: Run tests** — `python -m pytest tests/test_web.py -q` → all pass; then full suite.

- [ ] **Step 6: Commit** — `git commit -m "feat(web): Pro-dark index — black hero, frosted controls, dark cards"`

---

### Task 2: Emails (`digest.py`) — dark inline-styled templates

**Files:**
- Modify: `tests/test_digest.py` (append)
- Modify: `aggregator/digest.py`

- [ ] **Step 1: Append failing test**

```python
def test_email_is_dark_scheme():
    html = render_email_html(_EVENTS, TODAY)       # reuse existing fixture names
    assert 'name="color-scheme" content="dark"' in html
    assert 'bgcolor="#000000"' in html
    assert "#1d1d1f" in html                       # dark card surface
```

- [ ] **Step 2: Run — expect 3-assertion FAIL.**

- [ ] **Step 3: Re-point constants and dark-proof the wrapper**

```python
_E_BG = "#000000"      # page background
_E_CARD = "#1d1d1f"    # content card
_E_ACCENT = "#2997ff"  # links / section headers
_E_INK = "#f5f5f7"     # primary text
_E_MUTED = "#a1a1a6"   # secondary text (AA on dark)
_E_PILL = "#2c2c2e"    # date pill background
```

In `render_email_html` (and verify/welcome renderers):
- `<head>`: add `<meta name="color-scheme" content="dark"><meta name="supported-color-schemes" content="dark">`.
- Outer table: add ` bgcolor="#000000"` attribute (Outlook) alongside the inline style.
- Inner 600px card table: `background:#1d1d1f;border:1px solid #424245`.
- Header band `<tr>`: background `#000`, title color `#f5f5f7`, subtitle `#a1a1a6` (replace the blue band + `#cfe0ff`).
- CTA buttons: `background:#2997ff;color:#000;border-radius:980px`.
- Star span color `#d62728` → `#ff453a`; row separators `#eef0f5` → `#424245`.
- Footer text/links `#86868b`/`#a1a1a6`.
- `render_verify_email_html` / `render_welcome_email_html`: same constants flow through; update any hardcoded band/button/borders to the values above.
- DO NOT touch: text/plain rendering, recipient logic, unsubscribe URL plumbing, table structure.

- [ ] **Step 4: Run tests** — digest tests + full suite green.

- [ ] **Step 5: Commit** — `git commit -m "feat(email): Pro-dark weekly/welcome/verify templates (color-scheme dark, Outlook bgcolor)"`

---

### Task 3: Map (`emit.py`) — dark tiles, frosted nav, dark popups

**Files:**
- Modify: `tests/test_emit.py` (append; create the test fn wherever map tests live — check `grep -rn "_MAP_HEAD\|map.html" tests/`)
- Modify: `aggregator/emit.py` (`_MAP_HEAD`, `_MAP_TAIL`)

- [ ] **Step 1: Append failing test**

```python
def test_map_uses_dark_tiles():
    head = emit._MAP_HEAD
    assert "basemaps.cartocdn.com/dark_all" in (head + emit._MAP_TAIL)
    assert "#1d1d1f" in head
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Apply changes**

- Tile layer (in `_MAP_TAIL` JS): `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png`, attribution `&copy; OpenStreetMap contributors &copy; CARTO`.
- `_MAP_HEAD` CSS: same token mapping as Task 1 (`--ink:#f5f5f7`, bg `#000`, panel/cards `#1d1d1f`, borders `#424245`, accent `#2997ff`); nav bar = frosted dark like `.controls`.
- Add popup overrides:

```css
.leaflet-popup-content-wrapper,.leaflet-popup-tip{background:#1d1d1f;color:#f5f5f7;
box-shadow:0 2px 14px rgba(0,0,0,.6)}
.leaflet-popup-content a{color:#2997ff}
```

- Pin/marker colors: default `#2997ff`, big-name `#ff453a` (wherever the current palette colors markers).

- [ ] **Step 4: Run tests; full suite.**

- [ ] **Step 5: Commit** — `git commit -m "feat(map): Pro-dark map — CARTO dark tiles, dark popups and nav"`

---

### Task 4: Subscribe pages (`subscribe_server.py`) + status (`health.py`)

**Files:** Modify both; no new tests (covered by existing structural tests; these are internal/minor pages).

- [ ] **Step 1:** In `subscribe_server.py`, find the confirm/result page template(s) (`grep -n "<style\|<html" aggregator/subscribe_server.py`) and apply the token mapping: body `#000`/`#f5f5f7`, card `#1d1d1f` radius 16 border `#424245`, button accent pill w/ black text.
- [ ] **Step 2:** In `health.py` `render_status_html`: body `#000`/`#f5f5f7`, table rows `#1d1d1f`, borders `#424245`, status colors ok `#30d158` / empty `#ffd60a` / error `#ff453a`, links `#2997ff`.
- [ ] **Step 3:** Full suite green.
- [ ] **Step 4: Commit** — `git commit -m "feat(ui): Pro-dark subscribe + status pages"`

---

### Task 5: Verify, deploy, audit

- [ ] **Step 1:** Full suite locally (expect 404 + 3 new = 407).
- [ ] **Step 2:** Render index+map+digest locally to a temp dir, screenshot via chrome-devtools, compare against approved mockups (hero copy, pills, dark cards, popups).
- [ ] **Step 3:** Deploy changed files (tar→ssh per repo convention) + trigger `dc-frontier-events.service`; confirm live https://events.emersus.ai/ serves dark index, map.html dark tiles, and the dry-run `email/digest-<today>.eml` uses the dark template.
- [ ] **Step 4:** Lighthouse (chrome-devtools `lighthouse_audit`) on live index.html and map.html → expect 100/100/100/100; fix any contrast finding by bumping the flagged color one step lighter (e.g. `#86868b`→`#a1a1a6`).
- [ ] **Step 5:** `git push`; CI green; report before/after to user.
