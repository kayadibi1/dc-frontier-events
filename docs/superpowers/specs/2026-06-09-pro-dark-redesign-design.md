# "Pro dark" Apple redesign — all user-facing surfaces

**Date:** 2026-06-09 · **Status:** approved (visual companion session: direction
"C — Pro dark" chosen over apple.com-editorial and HIG-light; emails also dark,
"A — dark email" chosen with re-tint risk accepted)

## Goal

Restyle every interface — landing page, map, weekly/welcome/verify emails,
subscribe confirm pages, ops status page — in Apple's "Pro" dark design
language. Zero functional change: same filters, search, signup flow, feeds,
deliverability machinery, accessibility behavior.

## Design tokens (single set, all surfaces)

| Token | Value | Use |
|---|---|---|
| canvas | `#000000` | page background |
| surface | `#1d1d1f` | cards, nav, form fields |
| border | `#424245` | card/nav hairlines (1px) |
| text | `#f5f5f7` | primary text |
| muted | `#86868b` | secondary text (AA on canvas and surface) |
| muted-2 | `#a1a1a6` | secondary text where #86868b would sit on #424245 fills |
| accent | `#2997ff` | links, primary pills (black text on accent), selected states |
| big-name | `#ff453a` | ★ big-name markers (Apple dark systemRed) |
| radius | 14–16px cards, `980px` pills | |
| type | existing `-apple-system…` stack; headings `letter-spacing:-.02em`, weight 700 | |

Dark-only. No `prefers-color-scheme` toggle.

## Per-surface treatment

**Landing page (`web.py _CARD_CSS` + hero markup in `render_index`).** Gradient
hero replaced by left-aligned black hero: H1 "AI events in DC." + muted second
line "Tracked. Verified. Ranked.", stats row, accent pill Subscribe (scrolls to
signup) + ghost pills (Google Calendar / .ics / RSS / Map). Sticky controls bar
becomes frosted dark (`rgba(29,29,31,.72)` + `backdrop-filter:blur(12px)`).
Chips: unselected `#1d1d1f`/border `#424245`; selected = light inversion
(`#f5f5f7` bg, `#1d1d1f` text). Day-group cards become `#1d1d1f` rounded-16
cards (one card per event, day headers muted uppercase). Badges re-tinted dark
(virtual = accent-tinted `rgba(41,151,255,.16)`; in-person = green-tinted
`rgba(48,209,88,.16)` text `#30d158`; big = `rgba(255,69,58,.16)` text
`#ff453a`). Signup card + spamnote re-tinted on surface (spamnote keeps its
class name; amber becomes `rgba(255,214,10,.12)` text `#ffd60a`-dark-adjusted
for AA). All class names, DOM structure, data-* attributes, JS, JSON-LD, meta
description, `<main>` landmark unchanged.

**Map (`emit.py _MAP_HEAD`/`_MAP_TAIL`).** Tile layer switches to CARTO
dark_matter (`https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png`,
attribution "© OpenStreetMap contributors © CARTO"). Nav/list panel re-tokened
dark; Leaflet popup styled via `.leaflet-popup-content-wrapper`/`.leaflet-popup-tip`
overrides (`#1d1d1f`, text `#f5f5f7`). Pin colors: accent default, big-name red.

**Emails (`digest.py`).** `_E_*` constants re-pointed: BG `#000000`, CARD
`#1d1d1f`, ACCENT `#2997ff`, INK `#f5f5f7`, MUTED `#a1a1a6` (AA on dark
surfaces), PILL `#2c2c2e`. Header band: black with white title (no blue band).
Primary CTA pill: accent bg, **black** text, `border-radius:980px`. Star color
→ `#ff453a`. Add `<meta name="color-scheme" content="dark">` +
`<meta name="supported-color-schemes" content="dark">` and `bgcolor="#000000"`
attribute on the outer table (Outlook). Verify + welcome emails inherit via the
same constants; their hardcoded band/button styles updated to match. text/plain
parts, List-Unsubscribe headers, POST endpoints, recipient logic: untouched.

**Subscribe confirm/unsubscribe pages (`subscribe_server.py`).** Same tokens on
the small confirm-form pages; button = accent pill with black text.

**Status page (`health.py`).** Mechanical re-token (internal page): dark canvas,
surface table, status colors ok `#30d158` / empty `#ffd60a` / error `#ff453a`.

## Constraints

- WCAG-AA contrast everywhere (preserve Lighthouse 100/100/100/100 on index + map).
- No copy changes except the hero tagline.
- Email markup stays table-based with inline styles only.
- Feeds (.ics/RSS/JSON), favicon SVG, signup/verify flows byte-identical in behavior.

## Verification

1. Full pytest suite (only style-value assertions, if any, may need updating —
   known: none pin colors; `spamnote` class name is kept).
2. chrome-devtools Lighthouse on deployed index.html + map.html → 100/100/100/100.
3. Visual: screenshots of index, map, and the dry-run digest .eml the build
   writes, checked against the approved mockups.
4. Deploy to box, trigger build, confirm live pages serve the dark design.
