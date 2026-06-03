import os

from scripts.build_site import (
    DOMAIN,
    _heartbeat,
    _site_dir,
    render_index,
    write_site_extras,
)


def test_domain_is_the_subdomain():
    assert DOMAIN == "events.emersus.ai"


def test_site_dir_defaults_and_env_override(monkeypatch):
    monkeypatch.delenv("SITE_DIR", raising=False)
    assert _site_dir() == "site"
    monkeypatch.setenv("SITE_DIR", "/var/www/events.emersus.ai")
    assert _site_dir() == "/var/www/events.emersus.ai"


def test_render_index_has_subscribe_url_and_instructions():
    html = render_index("events.emersus.ai", "2026-05-30")
    assert "https://events.emersus.ai/events-upcoming.ics" in html  # fallback URL still shown
    assert "Google Calendar" in html
    assert "subscri" in html.lower()                                 # subscribe/subscription wording
    assert "2026-05-30" in html


def test_render_index_has_add_to_gcal_button():
    html = render_index("events.emersus.ai", "2026-05-30")
    # one-click Google Calendar subscribe: the cid MUST carry the webcal:// URL
    # (Google rejects an https:// cid with "Unable to add this calendar"), and
    # no /u/0/ (that forces the first signed-in account).
    assert "calendar.google.com/calendar/r?cid=" in html
    assert "/u/0/" not in html
    assert "cid=webcal%3A%2F%2Fevents.emersus.ai%2Fevents-upcoming.ics" in html
    assert "Add to Google Calendar" in html


def test_render_index_has_webcal_for_apple_outlook():
    html = render_index("events.emersus.ai", "2026-05-30")
    # webcal:// triggers a one-click subscribe in Apple Calendar / Outlook
    assert "webcal://events.emersus.ai/events-upcoming.ics" in html


def test_render_index_lists_all_feeds():
    html = render_index("x.example", "2026-05-30")
    for fn in ("events-upcoming.ics", "events.ics", "events-big-names.ics", "feed-upcoming.xml"):
        assert f"https://x.example/{fn}" in html


def test_render_index_has_signup_form():
    html = render_index("events.emersus.ai", "2026-05-30")
    assert 'action="/api/subscribe"' in html      # posts to the subscribe endpoint
    assert 'name="email"' in html
    assert 'name="website"' in html               # honeypot field present
    assert "weekly digest" in html.lower()


def test_render_index_has_attribution():
    html = render_index("events.emersus.ai", "2026-05-30")
    assert "Sidar Aslanoglu" in html
    assert "linkedin.com/in/sidar-aslanoglu" in html


def test_render_index_has_spam_note():
    # Deliverability nudge near the signup form (new sending domain -> Outlook junks).
    html = render_index("events.emersus.ai", "2026-05-30")
    assert "spamnote" in html
    assert "spam" in html.lower() and "Not junk" in html


def test_write_site_extras_writes_favicon(tmp_path):
    # index.html is now written by the pipeline (aggregator.web.render_index);
    # write_site_extras owns the favicon (+ credentials when present).
    d = str(tmp_path / "site")
    write_site_extras(d, "events.emersus.ai", "2026-05-30")
    assert os.path.exists(os.path.join(d, "favicon.svg"))


def test_heartbeat_noop_without_url(monkeypatch):
    # No HEALTHCHECK_URL set -> no ping attempted, returns False, never raises.
    monkeypatch.delenv("HEALTHCHECK_URL", raising=False)
    assert _heartbeat() is False


def test_heartbeat_pings_configured_url(monkeypatch):
    calls = []
    monkeypatch.setattr("scripts.build_site.urllib.request.urlopen",
                        lambda url, timeout=10: calls.append(url))
    assert _heartbeat("https://hc.example/ping/abc") is True
    assert calls == ["https://hc.example/ping/abc"]


def test_heartbeat_swallows_errors(monkeypatch):
    def boom(url, timeout=10):
        raise OSError("network down")
    monkeypatch.setattr("scripts.build_site.urllib.request.urlopen", boom)
    # Best-effort: a failed ping must not raise and must report False.
    assert _heartbeat("https://hc.example/ping/abc") is False
