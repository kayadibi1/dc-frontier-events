"""Render a simple, glanceable ops dashboard (Pro-dark) from the Caddy access
logs + subscribers.db. Replaces the dense GoAccess report at /ops/.

Stdlib only. Run on the box (root, to read the 600 caddy log + subscribers.db):
    python3 tools/ops_dashboard.py
Writes /opt/dc-frontier-events/ops/visitors.html.
"""

from __future__ import annotations

import glob
import gzip
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html import escape
from urllib.parse import urlsplit

LOG_GLOB = "/var/log/caddy/events-access.log*"
SUBS_DB = "/opt/dc-frontier-events/data/subscribers.db"
OUT = "/opt/dc-frontier-events/ops/visitors.html"

# Our own traffic + machines, excluded from "visitors".
EXCLUDE_IPS = {"73.173.160.170", "37.27.242.32"}
# Non-human user agents: crawlers, tools, monitors, and calendar pollers (the
# last are counted separately as subscription signals, not visitors).
BOT_UA = ("bot", "spider", "crawl", "slurp", "monitor", "uptime", "curl",
          "python", "wget", "go-http", "okhttp", "java/", "libwww", "ahrefs",
          "semrush", "headless", "censys", "expanse", "zgrab", "yak/",
          "google-calendar", "dataaccessd", "calendaragent", "davx", "ics/",
          "facebookexternal", "discord", "slack")
# Asset paths excluded from "top pages" so the list shows real pages.
ASSET_SUFFIX = (".svg", ".ico", ".png", ".css", ".js", ".webmanifest",
                ".json", ".xml", ".txt")


def _rows(paths):
    for f in sorted(paths):
        op = gzip.open if f.endswith(".gz") else open
        try:
            for line in op(f, "rt", errors="replace"):
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except ValueError:
                        pass
        except OSError:
            pass


def _ua(r):
    return (r.get("request", {}).get("headers", {}).get("User-Agent", [""]) or [""])[0]


def _ref(r):
    return (r.get("request", {}).get("headers", {}).get("Referer", [""]) or [""])[0]


def _ip(r):
    return r.get("request", {}).get("client_ip", "")


def _path(r):
    return r.get("request", {}).get("uri", "").split("?")[0]


def _is_bot(ua):
    ua = ua.lower()
    return (not ua) or any(b in ua for b in BOT_UA)


def collect(log_glob=LOG_GLOB):
    rows = list(_rows(glob.glob(log_glob)))
    m = {"total": len(rows), "human_hits": 0, "signups": 0, "cal_pulls": 0}
    times, per_day, pages, refs = [], defaultdict(set), Counter(), Counter()
    human_ips, gcal_ips, apple_ips = set(), set(), set()
    for r in rows:
        ts = r.get("ts", 0)
        if ts:
            times.append(ts)
        ua, ip, path = _ua(r), _ip(r), _path(r)
        if path == "/api/subscribe" and r.get("request", {}).get("method") == "POST":
            m["signups"] += 1
        if path.endswith(".ics"):
            m["cal_pulls"] += 1
        ual = ua.lower()
        if "google-calendar" in ual:
            gcal_ips.add(ip)
        if "dataaccessd" in ual or "calendaragent" in ual:
            apple_ips.add(ip)
        if _is_bot(ua) or ip in EXCLUDE_IPS:
            continue
        m["human_hits"] += 1
        human_ips.add(ip)
        day = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d") if ts else "?"
        per_day[day].add(ip)
        if not path.endswith(ASSET_SUFFIX):
            pages[path or "/"] += 1
        host = urlsplit(_ref(r)).netloc
        if host and "events.emersus.ai" not in host:
            refs[host] += 1
    m["unique_visitors"] = len(human_ips)
    m["per_day"] = sorted((d, len(ips)) for d, ips in per_day.items())
    m["top_pages"] = pages.most_common(7)
    m["top_referrers"] = refs.most_common(6)
    m["gcal_ips"], m["apple_ips"] = len(gcal_ips), len(apple_ips)
    if times:
        m["start"] = datetime.fromtimestamp(min(times), timezone.utc)
        m["end"] = datetime.fromtimestamp(max(times), timezone.utc)
        m["hours"] = (max(times) - min(times)) / 3600
    else:
        m["start"] = m["end"] = None
        m["hours"] = 0
    return m


def subscriber_counts(db=SUBS_DB):
    try:
        c = sqlite3.connect(db)
        v = c.execute("SELECT COUNT(*) FROM subscribers WHERE status='verified'").fetchone()[0]
        p = c.execute("SELECT COUNT(*) FROM subscribers WHERE status='pending'").fetchone()[0]
        c.close()
        return v, p
    except sqlite3.Error:
        return 0, 0


_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#000;color:#f5f5f7;font-family:-apple-system,'Segoe UI',system-ui,Roboto,Arial,sans-serif;
 line-height:1.5;padding:32px 20px;max-width:880px;margin:0 auto}
h1{font-size:22px;letter-spacing:-.02em;font-weight:700}
.sub{color:#86868b;font-size:13px;margin:4px 0 26px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:26px}
.card{background:#1d1d1f;border:1px solid #424245;border-radius:14px;padding:16px 18px}
.card .n{font-size:34px;font-weight:700;letter-spacing:-.02em}
.card .n.accent{color:#2997ff}
.card .l{color:#86868b;font-size:12px;text-transform:uppercase;letter-spacing:.04em;margin-top:2px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:#86868b;margin:24px 0 10px;font-weight:600}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:24px}
@media(max-width:620px){.grid2{grid-template-columns:1fr}}
.bar{display:flex;align-items:center;gap:10px;margin:7px 0;font-size:14px}
.bar .lab{flex:0 0 92px;color:#d2d2d7;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar .track{flex:1;background:#26262a;border-radius:6px;height:10px;overflow:hidden}
.bar .fill{display:block;background:#2997ff;height:100%;border-radius:6px}
.bar .v{flex:0 0 auto;color:#86868b;font-size:13px;width:34px;text-align:right}
.row{display:flex;justify-content:space-between;font-size:14px;padding:6px 0;border-bottom:1px solid #1d1d1f}
.row span:last-child{color:#86868b}
.empty{color:#86868b;font-size:13px;font-style:italic}
.foot{color:#56565a;font-size:12px;margin-top:30px}
"""


def _bars(items):
    if not items:
        return '<div class="empty">none yet</div>'
    mx = max(v for _, v in items) or 1
    out = []
    for label, v in items:
        w = round(100 * v / mx)
        out.append(f'<div class="bar"><span class="lab">{escape(str(label))}</span>'
                   f'<span class="track"><span class="fill" style="width:{w}%"></span></span>'
                   f'<span class="v">{v}</span></div>')
    return "".join(out)


def _rows_list(items):
    if not items:
        return '<div class="empty">none yet</div>'
    return "".join(f'<div class="row"><span>{escape(str(k))}</span><span>{v}</span></div>'
                   for k, v in items)


def render_html(m, verified, pending, now):
    if m["start"]:
        win = (f'{m["start"]:%b %d %H:%M} to {m["end"]:%b %d %H:%M} UTC '
               f'({m["hours"]:.0f}h)')
    else:
        win = "no traffic logged yet"
    per_day = _bars([(d[5:], n) for d, n in m["per_day"]])  # MM-DD
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>DC AI Radar - Ops</title><style>{_CSS}</style></head><body>
<h1>DC AI Radar - Ops</h1>
<div class="sub">{escape(win)} - generated {now:%Y-%m-%d %H:%M} UTC</div>

<div class="cards">
<div class="card"><div class="n accent">{verified}</div><div class="l">Verified subscribers</div></div>
<div class="card"><div class="n">{pending}</div><div class="l">Pending</div></div>
<div class="card"><div class="n">{m['unique_visitors']}</div><div class="l">Unique visitors</div></div>
<div class="card"><div class="n">{m['signups']}</div><div class="l">Signups</div></div>
</div>

<h2>Visitors per day</h2>
{per_day}

<div class="grid2">
<div><h2>Top pages</h2>{_rows_list(m['top_pages'])}</div>
<div><h2>Referrers</h2>{_rows_list(m['top_referrers'])}</div>
</div>

<h2>Calendar subscribers (polling the feed)</h2>
<div class="row"><span>Google Calendar</span><span>{m['gcal_ips']}</span></div>
<div class="row"><span>Apple Calendar</span><span>{m['apple_ips']}</span></div>
<div class="row"><span>Total .ics feed pulls</span><span>{m['cal_pulls']}</span></div>

<div class="foot">Visitors = distinct browser IPs, crawlers and our own traffic excluded.
Calendar counts are approximate (shared-feed clients dedupe); the verified-subscriber
number is the exact one.</div>
</body></html>"""


def main():
    import os
    m = collect()
    v, p = subscriber_counts()
    html = render_html(m, v, p, datetime.now(timezone.utc))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {OUT} ({m['unique_visitors']} visitors, {v} verified)")


if __name__ == "__main__":
    main()
