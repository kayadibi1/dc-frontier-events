from selectolax.parser import HTMLParser

from aggregator.digest import build_digest, render_email_html, render_html
from aggregator.models import Event


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
    assert "# DC AI & Semiconductor — Weekly Digest" in md
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
