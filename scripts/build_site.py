"""Build the publishable static site for the calendar subdomain.

Runs the aggregator into the output dir, then writes an index.html landing page
linking the feeds + the Google Calendar subscribe URL. Self-hosted on a Hetzner
box: a systemd timer runs this every 12h with SITE_DIR pointed at the Caddy web
root (e.g. /var/www/events.emersus.ai), and Caddy serves it over auto-HTTPS at
events.emersus.ai. No third-party host. Output dir is overridable via the
SITE_DIR env var (defaults to ./site for local preview). Pure render helpers
(render_index) are unit-tested without the pipeline.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import quote

# Allow running as a plain script ("python scripts/build_site.py"): ensure the
# repo root (this file's parent's parent) is importable so `aggregator` resolves.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aggregator.credentials import render_credentials_html
from aggregator.pipeline import run

DOMAIN = os.environ.get("CAL_DOMAIN", "events.emersus.ai")


def _site_dir() -> str:
    """Output dir for the built site. The systemd timer sets SITE_DIR to the web
    root; locally it defaults to ./site."""
    return os.environ.get("SITE_DIR", "site")

# (filename, label, blurb) for the landing page.
_FEEDS = [
    ("events-upcoming.ics", "events-upcoming.ics", "Subscribe to this in Google Calendar — upcoming events only."),
    ("events.ics", "events.ics", "Everything kept in the latest run."),
    ("events-big-names.ics", "events-big-names.ics", "Marquee orgs / people only."),
    ("feed-upcoming.xml", "feed-upcoming.xml", "Upcoming, as an RSS feed."),
]
_PAGES = [("credentials.html", "Prestige credentials, fellowships &amp; funding"),
          ("map.html", "Interactive map"), ("digest.html", "Weekly digest")]


def render_index(domain: str, today_iso: str) -> str:
    base = f"https://{domain}"
    sub = f"{base}/events-upcoming.ics"
    # webcal:// makes Apple Calendar / Outlook offer a one-click subscribe too.
    webcal = "webcal://" + sub.split("://", 1)[1]
    # One-click Google Calendar subscribe. The cid MUST use the webcal:// scheme:
    # Google's r?cid= endpoint rejects an https:// URL with "Unable to add this
    # calendar. Please check the URL." We also omit /u/0/ so Google adds it to the
    # active account rather than forcing the first signed-in one.
    gcal = f"https://calendar.google.com/calendar/r?cid={quote(webcal, safe='')}"
    feeds = "\n".join(
        f'  <li><a href="{base}/{fn}"><code>{label}</code></a> — {blurb}</li>'
        for fn, label, blurb in _FEEDS)
    pages = "\n".join(f'  <li><a href="{base}/{fn}">{label}</a></li>' for fn, label in _PAGES)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DC AI &amp; Frontier Tech Events</title>
<style>
body{{font-family:system-ui,Arial,sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem;line-height:1.55;color:#222}}
code{{background:#f3f3f7;padding:1px 5px;border-radius:4px;font-size:.95em}}
.box{{background:#eef3ff;border:1px solid #cdd9f5;border-radius:8px;padding:1rem 1.2rem;margin:1.3rem 0}}
a{{color:#1a4fd0}} h1{{margin-bottom:.2rem}} h2{{margin-top:1.6rem}} .sub{{color:#666}} ul{{padding-left:1.1rem}}
.gcal-btn{{display:inline-block;background:#1a73e8;color:#fff;font-weight:600;text-decoration:none;
padding:10px 18px;border-radius:8px;margin:.2rem 0}}
.gcal-btn:hover{{background:#1559b8}}
.alt{{display:inline-block;margin-left:.6rem}}
</style></head>
<body>
<h1>DC AI &amp; Frontier Tech Events</h1>
<p class="sub">Aggregated, deduped, and ranked AI / semiconductor / frontier-tech events in the
DC metro, tuned for AI-policy &amp; upskilling. Rebuilt automatically.</p>

<div class="box">
<a class="gcal-btn" href="{gcal}" target="_blank" rel="noopener">📅 Add to Google Calendar</a>
<a class="alt" href="{webcal}">Apple / Outlook</a>
<p class="sub" style="margin:.7rem 0 0">One click adds it as a subscription that auto-refreshes.
If the button doesn't take (Google can be picky), subscribe manually with
<i>Other calendars → From URL</i> and this address:<br>
<code>{sub}</code></p>
<p class="sub" style="margin:.4rem 0 0">Google re-polls the feed on its own schedule (typically every several hours).</p>
</div>

<h2>Feeds</h2>
<ul>
{feeds}
</ul>

<h2>Browse</h2>
<ul>
{pages}
</ul>

<p class="sub">Generated {today_iso}.</p>
</body></html>
"""


def write_site_extras(site_dir: str, domain: str, today_iso: str) -> None:
    """Write the landing index.html + the credentials subpage into site_dir.
    The credentials page is rendered from the credentials.json the pipeline just
    wrote (already merged with fetched deadlines/status); skipped if absent."""
    os.makedirs(site_dir, exist_ok=True)
    with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_index(domain, today_iso))
    cj = os.path.join(site_dir, "credentials.json")
    if os.path.exists(cj):
        with open(cj, encoding="utf-8") as f:
            cred_dicts = json.load(f)
        with open(os.path.join(site_dir, "credentials.html"), "w", encoding="utf-8") as f:
            f.write(render_credentials_html(cred_dicts, today_iso))


def build(today: str | None = None) -> None:
    today_iso = today or datetime.now(timezone.utc).date().isoformat()
    site_dir = _site_dir()
    run(out_dir=site_dir, db_path="data/events.db", today=today)
    write_site_extras(site_dir, DOMAIN, today_iso)
    print(f"[site] built {site_dir}/ for {DOMAIN} ({today_iso})")


if __name__ == "__main__":
    build()
