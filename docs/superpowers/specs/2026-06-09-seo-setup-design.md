# SEO setup for events.emersus.ai

**Date:** 2026-06-09 · **Status:** approved ("do it")

Baseline is already strong (meta/OG/twitter tags, ItemList JSON-LD, Lighthouse
SEO 100, fast static pages, HTTPS). This adds the missing crawler plumbing and
event-rich-result fields. All build-emitted, so it self-maintains.

## Changes

1. **`aggregator/seo.py` (new)** — pure renderers:
   - `ROBOTS_TXT`: allow all, `Disallow: /api/` + `/email/`, `Sitemap:` line.
   - `render_sitemap(today_iso)`: index (/), map.html, digest.html,
     credentials.html with `<lastmod>` = build date.
2. **`scripts/build_site.py write_site_extras`** writes `robots.txt` +
   `sitemap.xml` into the site dir each build.
3. **`aggregator/web.py`**: `<link rel="canonical" href="https://events.emersus.ai/">`;
   title gains "· Washington DC"; `_jsonld` items gain `endDate` (when known),
   `eventAttendanceMode` (Online when virtual, Offline when a real address),
   `organizer` (Organization), `eventStatus` EventScheduled.
4. **`aggregator/emit.py`**: canonical on map.html.
5. **`aggregator/digest.py render_html`**: canonical on digest.html.
6. **`aggregator/health.py`**: `<meta name="robots" content="noindex">` on the
   ops status page.

## Verification

TDD per change; full suite; deploy + rebuild; live checks: /robots.txt and
/sitemap.xml serve 200 with correct content, canonical present, Lighthouse SEO
still 100. Then hand the user the Google Search Console steps (their account):
add property, verify via Porkbun DNS TXT (or HTML file given to me), submit
sitemap.

## Out of scope

Per-event detail pages, Bing Webmaster, analytics. The status page stays
publicly reachable (noindex only).
