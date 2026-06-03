from aggregator.models import Event
from aggregator.web import _gcal_url, render_index


def _ev(**kw):
    base = dict(id="x", title="AI Policy Forum", start="2026-06-16", source="cset")
    base.update(kw)
    return Event(**base)


def test_renders_upcoming_events_and_subscribe_ctas():
    html = render_index([_ev()], "2026-06-02")
    assert "AI Policy Forum" in html
    assert "Add to Google Calendar" in html
    assert "events-upcoming.ics" in html
    assert "map.html" in html and "status.html" in html


def test_escapes_malicious_title():
    html = render_index([_ev(title="<script>alert(1)</script>")], "2026-06-02")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_big_name_gets_star():
    html = render_index([_ev(is_big_name=True, topics=["ai", "big:Nvidia"])], "2026-06-02")
    assert "★" in html


def test_past_events_excluded_and_empty_state():
    html = render_index([_ev(start="2020-01-01", title="Old Thing")], "2026-06-02")
    assert "Old Thing" not in html
    assert "No upcoming events" in html


def test_non_http_source_url_is_not_linked():
    html = render_index([_ev(source_url="javascript:alert(1)")], "2026-06-02")
    assert "javascript:alert(1)" not in html


def test_gcal_url_allday_and_timed_utc():
    assert "/render?" in _gcal_url(_ev(start="2026-06-16"))
    timed = _gcal_url(_ev(start="2026-06-16T12:00:00-04:00"))
    assert "20260616T160000Z" in timed          # 12:00 EDT -> 16:00 UTC
