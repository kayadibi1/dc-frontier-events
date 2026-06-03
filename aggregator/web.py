"""The public landing page (index.html): a polished, responsive, filterable list
of upcoming DC AI / semiconductor / frontier-tech events.

This is the product's flagship surface (the map is a secondary view). It is
server-rendered -- every event becomes an <article> card with data-* attributes --
plus a small vanilla-JS layer that filters by search / topic / layer / big-name /
in-person and hides empty date groups. Security: all dynamic text is HTML-escaped,
only http(s) source URLs become links, and the JS never uses innerHTML with event
data (textContent / data-attributes only), matching emit.py's hardening.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote_plus
from xml.sax.saxutils import escape

from .config import SOURCES
from .models import Event
from .provenance import marker

DOMAIN = "events.emersus.ai"
_NAME = {s.slug: s.name for s in SOURCES}
_LAYER = {s.slug: s.layer for s in SOURCES}
_LAYER_LABEL = {1: "Community", 2: "Policy", 3: "University"}


def _h(s: str) -> str:
    return escape(s or "", {'"': "&quot;"})


def _safe_url(u: str | None) -> str:
    u = (u or "").strip()
    lo = u.lower()
    return u if lo.startswith("http://") or lo.startswith("https://") else ""


def _real_topics(ev: Event) -> list[str]:
    return [t for t in ev.topics if not t.startswith("big:")]


def _is_virtual(ev: Event) -> bool:
    return bool(ev.raw.get("virtual")) and not ev.address


def _fmt_time(ev: Event) -> str:
    """'2:00 PM' for a timed start, '' for a date-only one."""
    s = ev.start or ""
    if len(s) <= 10:
        return ""
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return ""
    if dt.hour == 0 and dt.minute == 0:
        return ""   # midnight == all-day / unknown-time encoding, not a real start time
    return dt.strftime("%I:%M %p").lstrip("0")   # portable (no %-I); "02:00 PM"->"2:00 PM"


def _group_header(d: date, today: date) -> str:
    delta = (d - today).days
    if delta == 0:
        rel = "Today"
    elif delta == 1:
        rel = "Tomorrow"
    elif 2 <= delta <= 6:
        rel = "This week"
    elif 7 <= delta <= 13:
        rel = "Next week"
    else:
        rel = ""
    label = d.strftime("%A, %B ") + str(d.day)   # portable (no %-d)
    return f"{label}" + (f"  ·  {rel}" if rel else "")


def _gcal_dates(ev: Event) -> str:
    s = ev.start or ""
    # Date-only -> all-day range. MUST be handled before datetime.fromisoformat,
    # which (Py 3.11+) happily parses "2026-06-16" as midnight and would otherwise
    # emit a bogus 1-hour midnight event. Google all-day end is exclusive (+1 day).
    if len(s) <= 10 or "T" not in s:
        try:
            d = date.fromisoformat(s[:10])
        except ValueError:
            return ""
        end = None
        if ev.end:
            try:
                end = date.fromisoformat(ev.end[:10])
            except ValueError:
                end = None
        end = (end + timedelta(days=1)) if end else (d + timedelta(days=1))
        return f"{d.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return ""
    dt = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    start = dt.strftime("%Y%m%dT%H%M%SZ")
    end_dt = None
    if ev.end:
        try:
            e = datetime.fromisoformat(ev.end)
            end_dt = e.astimezone(timezone.utc) if e.tzinfo else e.replace(tzinfo=timezone.utc)
        except ValueError:
            end_dt = None
    end_dt = end_dt or dt + timedelta(hours=1)
    return f"{start}/{end_dt.strftime('%Y%m%dT%H%M%SZ')}"


def _gcal_url(ev: Event) -> str:
    dates = _gcal_dates(ev)
    if not dates:
        return ""
    params = [
        ("action", "TEMPLATE"),
        ("text", ev.title or "Event"),
        ("dates", dates),
        ("details", (ev.description or "") + (f"\n\n{ev.source_url}" if _safe_url(ev.source_url) else "")),
        ("location", ev.address or ("Virtual" if _is_virtual(ev) else "")),
    ]
    q = "&".join(f"{k}={quote_plus(v)}" for k, v in params if v)
    return "https://calendar.google.com/calendar/render?" + q


_CARD_CSS = """
*{box-sizing:border-box}
:root{--ink:#171a2b;--muted:#6b7280;--accent:#2348d6;--accent2:#7c3aed;
--bg:#f5f6fb;--card:#fff;--line:#e8e9f2;--chip:#eef1fb;--big:#d62728}
body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
background:var(--bg);color:var(--ink);line-height:1.45}
a{color:var(--accent)}
.hero{background:linear-gradient(135deg,#1b2a6b 0%,#2348d6 55%,#7c3aed 130%);color:#fff;
padding:30px 20px 26px}
.hero-in{max-width:920px;margin:0 auto}
.hero h1{font-size:25px;margin:0 0 4px;letter-spacing:-.01em}
.hero p{margin:0;color:#d7e0ff;font-size:14.5px;max-width:640px}
.stats{margin-top:14px;display:flex;gap:18px;flex-wrap:wrap;font-size:13px;color:#eaf0ff}
.stats b{font-size:18px;color:#fff;display:block;line-height:1}
.cta{margin-top:18px;display:flex;gap:9px;flex-wrap:wrap}
.btn{display:inline-flex;align-items:center;gap:6px;background:#fff;color:#1b2a6b;font-weight:600;
font-size:13.5px;text-decoration:none;padding:9px 14px;border-radius:9px;border:0;cursor:pointer}
.btn.ghost{background:rgba(255,255,255,.13);color:#fff;border:1px solid rgba(255,255,255,.35)}
.btn:hover{opacity:.93}
.wrap{max-width:920px;margin:0 auto;padding:18px 20px 60px}
.controls{position:sticky;top:0;background:var(--bg);padding:14px 0 10px;z-index:5;
border-bottom:1px solid var(--line)}
#q{width:100%;padding:11px 13px;border:1px solid var(--line);border-radius:10px;font-size:15px;
background:#fff}
.filters{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px;align-items:center}
.chip{border:1px solid var(--line);background:var(--card);color:#444;border-radius:999px;
padding:5px 12px;font-size:12.5px;cursor:pointer;user-select:none}
.chip.on{background:var(--accent);border-color:var(--accent);color:#fff}
.chip.topic.on{background:var(--accent2);border-color:var(--accent2)}
.sep{width:1px;height:20px;background:var(--line);margin:0 3px}
#count{color:var(--muted);font-size:12.5px;margin-top:9px}
.daygroup{margin-top:22px}
.dayhead{font-size:13px;font-weight:700;color:var(--muted);text-transform:uppercase;
letter-spacing:.04em;padding-bottom:7px;border-bottom:2px solid var(--line);margin-bottom:4px}
.card{display:flex;gap:14px;padding:14px 4px;border-bottom:1px solid var(--line)}
.card:hover{background:#fbfbff}
.when{flex:0 0 64px;text-align:center}
.when .d{font-size:21px;font-weight:800;line-height:1;color:var(--ink)}
.when .mo{font-size:11px;font-weight:700;text-transform:uppercase;color:var(--accent)}
.when .t{font-size:11px;color:var(--muted);margin-top:3px}
.body{flex:1;min-width:0}
.title{font-size:16px;font-weight:650;margin:0 0 3px;text-decoration:none;color:var(--ink)}
.title:hover{text-decoration:underline}
.title .star{color:var(--big)}
.meta{font-size:12.5px;color:var(--muted);display:flex;gap:7px;flex-wrap:wrap;align-items:center}
.tag{background:var(--chip);color:#3a44a8;border-radius:6px;padding:1px 7px;font-size:11px;font-weight:600}
.badge{border-radius:6px;padding:1px 7px;font-size:11px;font-weight:700}
.b-virtual{background:#e8f0ff;color:#1a55d6}.b-person{background:#e8f7ee;color:#137a3a}
.b-big{background:#ffe9e9;color:#c11}
.src{font-size:11.5px;color:#8a8fa3}
.addrow{margin-top:7px}
.addrow a{font-size:12px;color:var(--accent);text-decoration:none;font-weight:600}
.empty{padding:40px 0;text-align:center;color:var(--muted)}
footer{max-width:920px;margin:0 auto;padding:24px 20px 50px;color:var(--muted);font-size:12.5px;
border-top:1px solid var(--line)}
footer a{color:var(--muted)}
.signup{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:15px 18px;margin:16px 0 2px;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.signup h2{margin:0 0 3px;font-size:15.5px}
.signup .sub{margin:0 0 10px;font-size:13px;color:var(--muted)}
.signup form{display:flex;gap:8px;flex-wrap:wrap}
.signup input[type=email]{flex:1;min-width:220px;padding:10px 12px;border:1px solid var(--line);
border-radius:9px;font-size:15px}
.signup button{background:var(--accent);color:#fff;font-weight:600;border:0;border-radius:9px;
padding:10px 20px;font-size:14px;cursor:pointer}
.signup button:hover{opacity:.93}
.signup .hp{position:absolute;left:-9999px;width:1px;height:1px;opacity:0}
.spamnote{background:#fff6e5;border:1px solid #f3d9a4;border-radius:8px;padding:8px 10px;
margin:10px 0 0;font-size:12px;color:#5a4a2a;line-height:1.45}
@media(max-width:560px){.when{flex-basis:50px}.hero h1{font-size:21px}}
"""

# Email signup (double opt-in) -- posts to the subscribe server via Caddy. Plain
# string (literal braces). Includes the honeypot field the server checks for bots.
_SIGNUP_HTML = """
<div class="signup">
<h2>Prefer email? Get the weekly digest</h2>
<p class="sub">One curated email a week — new &amp; upcoming AI / chip / policy events in DC.
Confirm your address and we send a quick sample right away.</p>
<form method="post" action="/api/subscribe">
<input type="email" name="email" required placeholder="you@example.com" autocomplete="email" aria-label="Email address">
<input type="text" name="website" class="hp" tabindex="-1" autocomplete="off" aria-hidden="true">
<button type="submit">Subscribe</button>
</form>
<p class="spamnote">📬 <b>Check your spam/junk folder</b> for the confirmation email — if it landed there,
mark it <b>Not junk</b> so future digests reach your inbox.</p>
</div>"""


# Client filtering. A plain string (NOT an f-string) so its JS braces stay literal;
# inserted into the page via the {_INDEX_JS} slot. Event data reaches the DOM only
# through server-rendered, escaped data-* attributes -- this code reads attributes
# and toggles display, never building HTML from event text.
_INDEX_JS = """<script>
var cards=[].slice.call(document.querySelectorAll('.card'));
var q=document.getElementById('q');
var topics=new Set(), layers=new Set(['1','2','3']), flts=new Set();
function apply(){
  var term=q.value.toLowerCase().trim();
  var shown=0;
  cards.forEach(function(c){
    var ok=true;
    if(term && c.getAttribute('data-text').indexOf(term)<0) ok=false;
    if(ok && !layers.has(c.getAttribute('data-layer'))) ok=false;
    if(ok && flts.has('big') && c.getAttribute('data-big')!=='1') ok=false;
    if(ok && flts.has('person') && c.getAttribute('data-virtual')!=='0') ok=false;
    if(ok && topics.size){
      var ct=c.getAttribute('data-topics').split(' ');
      var hit=false; topics.forEach(function(t){ if(ct.indexOf(t)>=0) hit=true; });
      if(!hit) ok=false;
    }
    c.style.display=ok?'':'none'; if(ok) shown++;
  });
  [].slice.call(document.querySelectorAll('.daygroup')).forEach(function(g){
    var any=[].slice.call(g.querySelectorAll('.card')).some(function(c){return c.style.display!=='none';});
    g.style.display=any?'':'none';
  });
  document.getElementById('count').textContent=shown+' of '+cards.length+' events shown';
}
q.addEventListener('input',apply);
[].slice.call(document.querySelectorAll('.chip')).forEach(function(ch){
  ch.addEventListener('click',function(){
    if(ch.classList.contains('topic')){var t=ch.getAttribute('data-topic');
      if(topics.has(t)){topics.delete(t);ch.classList.remove('on');}else{topics.add(t);ch.classList.add('on');}}
    else if(ch.classList.contains('lyr')){var l=ch.getAttribute('data-layer');
      if(layers.has(l)){layers.delete(l);ch.classList.remove('on');}else{layers.add(l);ch.classList.add('on');}}
    else if(ch.classList.contains('flt')){var f=ch.getAttribute('data-flt');
      if(flts.has(f)){flts.delete(f);ch.classList.remove('on');}else{flts.add(f);ch.classList.add('on');}}
    apply();
  });
});
apply();
</script>"""


def _card(ev: Event, today: date) -> str:
    s = ev.start or ""
    try:
        d = date.fromisoformat(s[:10])
        mo, dnum = d.strftime("%b"), str(d.day)
    except ValueError:
        mo, dnum = "", s[:10]
    tm = _fmt_time(ev)
    url = _safe_url(ev.source_url)
    title = _h(ev.title)
    star = '<span class="star">★</span> ' if ev.is_big_name else ""
    title_html = (f'<a class="title" href="{_h(url)}" target="_blank" rel="noopener">{star}{title}</a>'
                  if url else f'<span class="title">{star}{title}</span>')
    topics = _real_topics(ev)
    tags = "".join(f'<span class="tag">{_h(t)}</span>' for t in topics)
    src = _h(_NAME.get(ev.source, ev.source))
    if _is_virtual(ev):
        badge = '<span class="badge b-virtual">virtual</span>'
        loc = ""
    else:
        badge = '<span class="badge b-person">in&#8209;person</span>' if ev.address else ""
        loc = _h(ev.address.split(",")[0]) + (" 📍approx" if marker(ev) else "") if ev.address else ""
    big = '<span class="badge b-big">★ big name</span>' if ev.is_big_name else ""
    meta_bits = [b for b in [big, badge, f'<span class="tag">{loc}</span>' if loc else "", tags] if b]
    meta = "".join(meta_bits)
    gcal = _gcal_url(ev)
    addrow = (f'<div class="addrow"><a href="{_h(gcal)}" target="_blank" rel="noopener">＋ Add to '
              f'Google Calendar</a></div>' if gcal else "")
    search = _h(" ".join([ev.title, src, " ".join(topics), ev.address or ""]).lower())
    return (
        f'<article class="card" data-text="{search}" data-layer="{_LAYER.get(ev.source, 1)}" '
        f'data-big="{1 if ev.is_big_name else 0}" data-virtual="{1 if _is_virtual(ev) else 0}" '
        f'data-topics="{_h(" ".join(topics))}">'
        f'<div class="when"><div class="mo">{mo}</div><div class="d">{dnum}</div>'
        f'<div class="t">{_h(tm)}</div></div>'
        f'<div class="body">{title_html}'
        f'<div class="meta"><span class="src">{src}</span>{meta}</div>{addrow}</div></article>')


def render_index(events: list[Event], today_iso: str, summary: dict | None = None) -> str:
    summary = summary or {}
    today = date.fromisoformat(today_iso)
    upcoming = sorted([e for e in events if (e.start or "")[:10] >= today_iso],
                      key=lambda e: e.start or "")
    n_big = sum(1 for e in upcoming if e.is_big_name)
    n_src = len({e.source for e in upcoming})
    all_topics = sorted({t for e in upcoming for t in _real_topics(e)})

    # group by date
    groups: dict[str, list[Event]] = {}
    for e in upcoming:
        groups.setdefault((e.start or "")[:10], []).append(e)
    body_parts = []
    for day_iso, evs in groups.items():
        try:
            d = date.fromisoformat(day_iso)
            head = _group_header(d, today)
        except ValueError:
            head = day_iso
        cards = "".join(_card(e, today) for e in evs)
        body_parts.append(f'<section class="daygroup"><div class="dayhead">{_h(head)}</div>{cards}</section>')
    body = "".join(body_parts) or '<div class="empty">No upcoming events match — try clearing filters.</div>'

    topic_chips = "".join(
        f'<span class="chip topic" data-topic="{_h(t)}">{_h(t)}</span>' for t in all_topics)
    healthy = summary.get("sources_healthy", n_src)
    total_src = summary.get("sources_total", len(SOURCES))

    sub = f"https://{DOMAIN}/events-upcoming.ics"
    webcal = f"webcal://{DOMAIN}/events-upcoming.ics"
    gcal_all = ("https://calendar.google.com/calendar/r?cid="
                + quote_plus(f"webcal://{DOMAIN}/events-upcoming.ics"))

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<title>DC AI &amp; Frontier Tech Events</title>
<meta name="description" content="A curated, deduplicated, ranked radar of AI, semiconductor and frontier-tech events across the Washington DC metro — think tanks, universities, and the builder community.">
<style>{_CARD_CSS}</style></head>
<body>
<div class="hero"><div class="hero-in">
<h1>DC AI &amp; Frontier Tech Events</h1>
<p>A curated radar of AI, semiconductor, and frontier-tech events across the DC metro —
think tanks, universities, and the builder community, deduplicated and ranked.</p>
<div class="stats">
<div><b>{len(upcoming)}</b> upcoming</div>
<div><b>{n_big}</b> big&#8209;name</div>
<div><b>{n_src}</b> sources</div>
<div><b>{healthy}/{total_src}</b> healthy</div>
</div>
<div class="cta">
<a class="btn" href="{gcal_all}" target="_blank" rel="noopener">📅 Add to Google Calendar</a>
<a class="btn ghost" href="{webcal}">🍎 Apple / Outlook</a>
<a class="btn ghost" href="events-upcoming.ics">⬇ .ics</a>
<a class="btn ghost" href="map.html">🗺 Map view</a>
<a class="btn ghost" href="feed-upcoming.xml">📡 RSS</a>
<a class="btn ghost" href="status.html">📊 Status</a>
</div>
</div></div>

<div class="wrap">
{_SIGNUP_HTML}
<div class="controls">
<input id="q" type="text" placeholder="Search events, speakers, venues…" autocomplete="off">
<div class="filters">
<span class="chip flt" data-flt="big">★ Big names</span>
<span class="chip flt" data-flt="person">In&#8209;person</span>
<span class="sep"></span>
<span class="chip lyr on" data-layer="2">Policy</span>
<span class="chip lyr on" data-layer="3">University</span>
<span class="chip lyr on" data-layer="1">Community</span>
<span class="sep"></span>
{topic_chips}
</div>
<div id="count"></div>
</div>
<div id="list">{body}</div>
</div>

<footer>
Aggregated from {total_src} sources across three layers · updated {_h(today_iso)} ·
data is deduplicated, ranked, and location-verified.<br>
Feeds: <a href="events.ics">all .ics</a> · <a href="events-big-names.ics">big-names .ics</a> ·
<a href="feed.xml">RSS</a> · <a href="events.json">JSON</a> · <a href="status.html">source health</a><br>
📍approx = pinned at the host venue when an exact address wasn't published.<br>
Curated by <a href="https://www.linkedin.com/in/sidar-aslanoglu/" target="_blank" rel="noopener">Sidar Aslanoglu</a>
· <a href="mailto:radar@emersus.ai">suggest an event</a>
</footer>
{_INDEX_JS}
</body></html>"""
