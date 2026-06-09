"""Crawler plumbing: robots.txt + sitemap.xml. Build-emitted each run so the
lastmod is always the current build date and the files can never go stale."""
from __future__ import annotations

DOMAIN = "events.emersus.ai"

ROBOTS_TXT = f"""User-agent: *
Allow: /
Disallow: /api/
Disallow: /email/

Sitemap: https://{DOMAIN}/sitemap.xml
"""

# The real, linkable pages. status.html (ops) is deliberately absent.
_PAGES = ("", "map.html", "digest.html", "credentials.html")


def render_sitemap(today_iso: str) -> str:
    urls = "".join(
        f"<url><loc>https://{DOMAIN}/{p}</loc><lastmod>{today_iso}</lastmod></url>"
        for p in _PAGES)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{urls}</urlset>\n")
