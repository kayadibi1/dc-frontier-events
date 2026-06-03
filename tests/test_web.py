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
    assert "webcal://events.emersus.ai/events-upcoming.ics" in html   # Apple/Outlook subscribe
    assert "map.html" in html and "status.html" in html
    assert "spamnote" in html                                         # deliverability nudge


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


def test_index_has_signup_form_and_attribution():
    html = render_index([_ev()], "2026-06-02")
    assert 'action="/api/subscribe"' in html      # email double-opt-in form
    assert 'name="website"' in html               # honeypot field preserved
    assert "weekly digest" in html.lower()
    assert "Sidar Aslanoglu" in html              # curator attribution


def test_index_has_social_meta_and_jsonld():
    html = render_index([_ev()], "2026-06-02")
    assert 'property="og:title"' in html
    assert 'name="twitter:card"' in html
    assert 'application/ld+json' in html
    assert '"ItemList"' in html and '"Event"' in html


def test_jsonld_neutralizes_script_breakout():
    html = render_index([_ev(title="x</script><script>alert(1)//")], "2026-06-02")
    # the </script> in a title must be escaped so it can't close the JSON-LD block
    assert "</script><script>alert(1)" not in html


def test_filter_chips_are_keyboard_accessible():
    html = render_index([_ev(topics=["ai"])], "2026-06-02")
    assert 'role="button"' in html and 'tabindex="0"' in html
    assert 'aria-pressed' in html
    assert "keydown" in html                       # Enter/Space activates a chip
    assert "<main" in html                         # one main landmark (a11y)


def test_gcal_url_allday_and_timed_utc():
    allday = _gcal_url(_ev(start="2026-06-16"))
    # date-only -> all-day range, NOT a fabricated midnight 1-hour event (Codex finding)
    assert "20260616%2F20260617" in allday
    assert "T000000Z" not in allday
    timed = _gcal_url(_ev(start="2026-06-16T12:00:00-04:00"))
    assert "20260616T160000Z" in timed          # 12:00 EDT -> 16:00 UTC
