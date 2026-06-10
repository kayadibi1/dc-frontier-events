"""Build the publishable static site for the calendar subdomain.

Runs the aggregator pipeline into the output dir -- which writes the rich,
filterable index.html (aggregator.web.render_index) plus every feed -- then adds
the favicon and the credentials subpage. Self-hosted on a Hetzner box: a systemd
timer runs this every 12h with SITE_DIR pointed at the Caddy web root (e.g.
/var/www/events.emersus.ai), and Caddy serves it over auto-HTTPS at
events.emersus.ai. No third-party host. Output dir is overridable via the SITE_DIR
env var (defaults to ./site for local preview).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.request
from datetime import datetime, timezone

# Allow running as a plain script ("python scripts/build_site.py"): ensure the
# repo root (this file's parent's parent) is importable so `aggregator` resolves.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aggregator.credentials import render_credentials_html
from aggregator.pipeline import run
from aggregator.seo import ROBOTS_TXT, render_sitemap

DOMAIN = os.environ.get("CAL_DOMAIN", "events.emersus.ai")


def _site_dir() -> str:
    """Output dir for the built site. The systemd timer sets SITE_DIR to the web
    root; locally it defaults to ./site."""
    return os.environ.get("SITE_DIR", "site")


# Brand favicon: a radar-sweep glyph in the Pro-dark accent blue (#2997ff). Self-
# contained SVG so the whole site has a crisp tab icon (pages reference it via
# <link rel="icon">). The raster home-screen icons (apple-touch-icon, the Android
# manifest 192/512 PNGs, favicon.ico) are rendered from THIS same glyph by
# scripts/gen_icons.py and shipped from scripts/assets/ -- see ICON_FILES below.
FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="14" fill="#2997ff"/>'
    '<g fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round">'
    '<path d="M19 45 A26 26 0 0 1 45 19"/><path d="M23 45 A18 18 0 0 1 41 27"/></g>'
    '<circle cx="19" cy="45" r="5" fill="#fff"/></svg>'
)


# Pre-rendered raster icons (from scripts/gen_icons.py), copied verbatim so the
# box build needs no image toolchain. apple-touch-icon(+precomposed) cover iOS;
# the 192/512 PNGs are the Android home-screen icons referenced by the manifest;
# favicon.ico is the legacy/`/favicon.ico` fallback browsers probe for by default.
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
ICON_FILES = (
    "favicon.ico",
    "apple-touch-icon.png",
    "apple-touch-icon-precomposed.png",
    "icon-192.png",
    "icon-512.png",
    "og-image.png",   # 1200x630 social/Twitter card image (PNG; X can't render SVG)
)

# PWA / Android home-screen manifest. theme/background are the Pro-dark canvas so
# the install splash matches the site; the 512 doubles as a maskable adaptive icon
# (the glyph sits well inside the safe zone, the accent bleeds to every edge).
SITE_WEBMANIFEST = json.dumps({
    "name": "DC AI & Frontier Tech Events",
    "short_name": "DC AI Radar",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#000000",
    "theme_color": "#000000",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png",
         "purpose": "any"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png",
         "purpose": "any maskable"},
    ],
}, indent=2)


def write_site_extras(site_dir: str, today_iso: str) -> None:
    """Add the favicon set (SVG + iOS/Android rasters + manifest), crawler files
    (robots/sitemap), and the credentials subpage to a freshly-built site dir. The
    landing index.html and all feeds are written by the pipeline run; the
    credentials page is rendered from the credentials.json it wrote (skipped if
    absent)."""
    os.makedirs(site_dir, exist_ok=True)
    with open(os.path.join(site_dir, "favicon.svg"), "w", encoding="utf-8") as f:
        f.write(FAVICON_SVG)
    for name in ICON_FILES:
        shutil.copyfile(os.path.join(ASSETS_DIR, name), os.path.join(site_dir, name))
    # Named .json (not .webmanifest) so Caddy serves it as application/json -- a
    # spec-valid manifest MIME; Caddy/Go has no MIME mapping for .webmanifest and
    # would serve an empty Content-Type that browsers may reject.
    with open(os.path.join(site_dir, "manifest.json"), "w", encoding="utf-8") as f:
        f.write(SITE_WEBMANIFEST)
    with open(os.path.join(site_dir, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(ROBOTS_TXT)
    with open(os.path.join(site_dir, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(render_sitemap(today_iso))
    cj = os.path.join(site_dir, "credentials.json")
    if os.path.exists(cj):
        with open(cj, encoding="utf-8") as f:
            cred_dicts = json.load(f)
        with open(os.path.join(site_dir, "credentials.html"), "w", encoding="utf-8") as f:
            f.write(render_credentials_html(cred_dicts, today_iso))


def _heartbeat(url: str | None = None) -> bool:
    """Ping a dead-man's-switch (e.g. healthchecks.io) so a *missed* run alerts us.
    Called only after a fully successful build, so a silent failure -- box down,
    timer disabled, pipeline wedged -- stops the pings and the monitor emails us.
    Best-effort: reads HEALTHCHECK_URL from the env, never raises, never blocks the
    build. Returns True if a ping was sent."""
    url = url or os.environ.get("HEALTHCHECK_URL")
    if not url:
        return False
    try:
        urllib.request.urlopen(url, timeout=10)
        print("[heartbeat] pinged monitor")
        return True
    except Exception as e:  # monitoring must never break the run
        print(f"[heartbeat] ping failed ({e!r}); ignored")
        return False


def build(today: str | None = None) -> None:
    today_iso = today or datetime.now(timezone.utc).date().isoformat()
    site_dir = _site_dir()
    run(out_dir=site_dir, db_path="data/events.db", today=today)
    write_site_extras(site_dir, today_iso)
    print(f"[site] built {site_dir}/ for {DOMAIN} ({today_iso})")
    _heartbeat()  # success ping last, so it only fires when everything above worked


if __name__ == "__main__":
    build()
