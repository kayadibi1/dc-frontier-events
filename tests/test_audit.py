import asyncio

from aggregator.audit import audit_events
from aggregator.models import Event
from aggregator.provenance import prov_set

T = "2026-06-02"
JSONLD = ('<script type="application/ld+json">{{"@type":"Event","name":"{name}",'
          '"startDate":"{start}"}}</script>')


async def _aret(html):
    return html


def _run(ev, html):
    return asyncio.run(audit_events([ev], lambda url, kind: _aret(html), T))[0]


def test_match():
    ev = Event(id="1", title="AI Policy Panel", start="2026-06-10T10:00:00-04:00", source="csis",
               source_url="http://x")
    row = _run(ev, JSONLD.format(name="AI Policy Panel", start="2026-06-10T10:00:00-04:00"))
    assert row["status"] == "read" and row["date"] == "match" and row["title_verdict"] == "match"


def test_date_mismatch():
    ev = Event(id="2", title="P", start="2026-06-10", source="csis", source_url="http://x")
    row = _run(ev, JSONLD.format(name="P", start="2026-06-17"))
    assert "mismatch" in row["date"]


def test_date_no_false_mismatch_csis_naive_utc():
    ev = Event(id="3", title="P", start="2026-06-04T22:00:00-04:00", source="csis", source_url="http://x")
    row = _run(ev, JSONLD.format(name="P", start="2026-06-05T02:00:00"))
    assert row["date"] == "match"


def test_title_punct_match_and_suffix_strip():
    ev = Event(id="4", title="AI & Chips: 2026", start="2026-06-10", source="csis", source_url="http://x")
    html = '<meta property="og:title" content="AI &amp; Chips 2026 | CSIS">'
    row = _run(ev, html)
    assert row["title_verdict"] == "match"


def test_title_mismatch():
    ev = Event(id="5", title="Old Title", start="2026-06-10", source="csis", source_url="http://x")
    row = _run(ev, JSONLD.format(name="Completely Different", start="2026-06-10"))
    assert row["title_verdict"] == "mismatch"


def test_unreadable_empty_and_raises():
    ev = Event(id="6", title="P", start="2026-06-10", source="csis", source_url="http://x")
    assert _run(ev, "")["status"] == "unreadable"

    async def boom(url, kind):
        raise OSError("down")
    row = asyncio.run(audit_events([ev], boom, T))[0]
    assert row["status"] == "unreadable"


def test_unverifiable_when_no_ground_truth():
    ev = Event(id="7", title="P", start="2026-06-10", source="csis", source_url="http://x")
    row = _run(ev, "<p>just text, no event markup</p>")
    assert row["date"] == "unverifiable" and row["title_verdict"] == "unverifiable"


def test_location_note_for_hq_with_live_venue():
    ev = Event(id="8", title="P", start="2026-06-10", source="csis", source_url="http://x",
               address="CSIS HQ")
    prov_set(ev, "location", "hq")
    html = ('<script type="application/ld+json">{"@type":"Event","name":"P","startDate":"2026-06-10",'
            '"location":{"@type":"Place","name":"Real Hall","address":{"@type":"PostalAddress",'
            '"streetAddress":"9 X St","addressLocality":"Washington","addressRegion":"DC","postalCode":"20001"}}}</script>')
    row = _run(ev, html)
    assert "live venue available" in row["location_note"]


def test_date_only_live_no_false_mismatch():
    ev = Event(id="9", title="P", start="2026-06-10T10:00:00-04:00", source="csis", source_url="http://x")
    row = _run(ev, JSONLD.format(name="P", start="2026-06-10"))
    assert row["date"] == "match"


def test_location_note_venue_only():
    ev = Event(id="10", title="P", start="2026-06-10", source="csis", source_url="http://x", address="CSIS HQ")
    prov_set(ev, "location", "hq")
    html = ('<script type="application/ld+json">{"@type":"Event","name":"P","startDate":"2026-06-10",'
            '"location":{"@type":"Place","name":"Real Hall"}}</script>')
    row = _run(ev, html)
    assert "Real Hall" in row["location_note"]


def test_render_audit_md_escapes_and_summarizes():
    from aggregator.audit import render_audit_md
    rows = [
        {"id": "1", "source": "csis", "title": "A | B", "status": "read",
         "date": "match", "title_verdict": "mismatch", "location_note": ""},
        {"id": "2", "source": "cnas", "title": "C", "status": "unreadable",
         "date": "", "title_verdict": "", "location_note": ""},
        {"id": "3", "source": "csis", "title": "D", "status": "read",
         "date": "unverifiable", "title_verdict": "unverifiable", "location_note": ""},
    ]
    md = render_audit_md(rows, "2026-06-02")
    assert "A \| B" in md
    assert "1 mismatch" in md and "1 unverifiable" in md and "1 unreadable" in md
