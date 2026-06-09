from selectolax.parser import HTMLParser

from aggregator.digest import (
    build_digest,
    render_email_html,
    render_html,
    render_verify_email_html,
    render_welcome_email_html,
)
from aggregator.models import Event


def test_render_verify_email_has_button_and_expiry():
    url = "https://events.emersus.ai/api/verify?token=abc123"
    html = render_verify_email_html(url)
    assert url in html                      # the verify link is present
    assert "Confirm my subscription" in html
    assert "48 hours" in html               # expiry disclosed
    assert "did not sign up" in html        # safe footer for misdelivery
    assert "<style>" not in html            # inline styles only (email-safe)


def test_render_welcome_email_has_taste_button_and_monday_pointer():
    evs = [
        Event(id="a", title="AI policy panel", start="2026-06-02", source="cset",
              topics=["ai", "policy"], source_url="https://cset.org/e/a"),
        Event(id="b", title="Chip workshop", start="2026-06-03", source="DC2",
              topics=["semiconductor"]),
        Event(id="c", title="Data center futures", start="2026-06-04", source="csis",
              topics=["ai", "compute"]),
        Event(id="d", title="Fourth event", start="2026-06-05", source="DC2", topics=["ai"]),
    ]
    html = render_welcome_email_html(evs, "2026-05-31", taste_n=3,
                                     unsubscribe_url="https://x/api/unsubscribe?token=z")
    assert "You" in html and "in." in html  # "You're in."
    # hero: add-to-google-calendar with the webcal cid
    assert "cid=webcal%3A%2F%2Fevents.emersus.ai%2Fevents-upcoming.ics" in html
    # taste = exactly 3 events (the 4th must not appear)
    assert "AI policy panel" in html
    assert "Fourth event" not in html
    # explicitly points at Monday's digest so the weekly send isn't redundant
    assert "Monday" in html
    assert "api/unsubscribe?token=z" in html


def test_render_welcome_email_safe_when_no_events():
    html = render_welcome_email_html([], "2026-05-31")
    assert "You" in html
    assert "Monday" in html                 # still nudges to the weekly digest


def test_render_email_html_has_sections_button_and_new_block():
    big = Event(id="b1", title="Anthropic policy talk", start="2026-06-01",
                source="cset", source_url="https://cset.georgetown.edu/e/1",
                topics=["ai", "policy"], is_big_name=True)
    other = Event(id="o1", title="AI builders meetup", start="2026-06-03",
                  source="DC2", topics=["ai"])
    html = render_email_html([big, other], "2026-05-31", new_events=[other],
                             domain="events.emersus.ai")
    # the three sections
    assert "New this week (1)" in html
    assert "Big names" in html and "Top upcoming" in html
    # one-click subscribe button with the webcal cid (same rule as the site button)
    assert "cid=webcal%3A%2F%2Fevents.emersus.ai%2Fevents-upcoming.ics" in html
    # the new event appears, with a Jun / 03 date pill
    assert "AI builders meetup" in html
    assert ">Jun<" in html and ">03<" in html
    # email-client-safe: inline styles only, no <style> block
    assert "<style>" not in html


def test_render_email_html_excludes_past_new_events():
    past = Event(id="p1", title="Old talk", start="2026-01-01", source="DC2")
    html = render_email_html([past], "2026-05-31", new_events=[past])
    assert "New this week (0)" in html            # past event not counted as new
    assert "Nothing new since last week" in html  # empty-state copy shown


def test_render_email_html_safe_when_empty():
    html = render_email_html([], "2026-05-31", new_events=[])
    assert "No upcoming events in range." in html
    assert "Nothing new since last week" in html

TODAY = "2026-05-29"


def mk(**kw):
    base = dict(id="x", title="t", start="2026-06-01", source="DC2")
    base.update(kw)
    return Event(**base)


def test_digest_lists_upcoming_ranked_and_excludes_past():
    evs = [
        mk(id="past", title="Old AI Talk", start="2024-01-01", topics=["ai"]),
        mk(id="low", title="Plain AI Meetup", start="2026-06-02", topics=["ai"]),
        mk(id="high", title="Chip Policy Panel", start="2026-06-02",
           topics=["ai", "semiconductor"], source="csis"),
    ]
    md = build_digest(evs, TODAY)
    assert "# DC AI & Frontier Tech — Weekly Digest" in md
    assert "Old AI Talk" not in md            # past excluded
    assert "Chip Policy Panel" in md and "Plain AI Meetup" in md
    # higher-scored event appears before the lower one in the ranked list
    assert md.index("Chip Policy Panel") < md.index("Plain AI Meetup")
    assert "2 upcoming event(s)" in md


def test_digest_big_names_section():
    with_big = build_digest([mk(title="Fireside", topics=["ai"], is_big_name=True)], TODAY)
    assert "## ⭐ Big names" in with_big
    assert "Fireside" in with_big.split("## Top upcoming")[0]  # listed under Big names

    without = build_digest([mk(title="Plain", topics=["ai"])], TODAY)
    assert "None scheduled in range" in without


def test_digest_handles_empty():
    md = build_digest([], TODAY)
    assert "0 upcoming event(s)" in md
    assert "No upcoming events in range" in md


def test_render_html_ranked_and_parses():
    evs = [
        mk(id="past", title="Old AI Talk", start="2024-01-01", topics=["ai"]),
        mk(id="low", title="Plain AI Meetup", start="2026-06-02", topics=["ai"]),
        mk(id="big", title="Fireside with Nvidia", start="2026-06-02",
           topics=["ai"], is_big_name=True, source="csis"),
    ]
    html = render_html(evs, TODAY)
    tree = HTMLParser(html)
    assert tree.css_first("h1") is not None
    assert "Old AI Talk" not in html                     # past excluded
    assert "Fireside with Nvidia" in html and "Plain AI Meetup" in html
    # big-name event appears in the Big names section (before Top upcoming)
    assert html.index("Fireside with Nvidia") < html.index("Top upcoming")
    assert "<style>" in html                             # self-contained


def test_digest_loc_shows_approx_marker():
    from aggregator.digest import _loc
    from aggregator.provenance import prov_set
    ev = Event(id="d", title="x", start="2026-06-10", source="csis", address="CSIS HQ addr")
    prov_set(ev, "location", "hq")
    assert "📍approx" in _loc(ev)
    ev2 = Event(id="d2", title="x", start="2026-06-10", source="brookings", address="Real Venue")
    prov_set(ev2, "location", "scraped")
    assert "📍approx" not in _loc(ev2)


def test_email_is_dark_scheme():
    evs = [Event(id="a", title="AI policy panel", start="2026-06-20", source="cset",
                 topics=["ai"])]
    html = render_email_html(evs, "2026-06-09")
    assert 'name="color-scheme" content="dark"' in html
    assert 'bgcolor="#000000"' in html      # Outlook-safe dark canvas
    assert "#1d1d1f" in html                # dark card surface


def test_email_buttons_survive_css_stripping():
    # Outlook's Word renderer drops CSS background on <a> but honors the
    # bgcolor attribute on table cells -> buttons must carry bgcolor.
    evs = [Event(id="a", title="AI panel", start="2026-06-20", source="cset",
                 topics=["ai"])]
    html = render_email_html(evs, "2026-06-09")
    assert 'bgcolor="#2997ff"' in html
    v = render_verify_email_html("https://x/api/verify?token=t")
    assert 'bgcolor="#2997ff"' in v
