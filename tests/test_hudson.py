from aggregator.fetchers.hudson import parse_hudson_date, parse_hudson_listing

# Mirrors the real Hudson listing DOM: an empty image-wrapper anchor to the
# /events/<slug>, the title in <h3>, and "Past Event"/"Event" labels (no date).
LISTING = """
<div class="grid">
  <article class="group">
    <a class="absolute inset-0" href="/events/ai-chips-compute-technology-competition-china"></a>
    <div><span>Event</span>
      <h3>AI, Chips, and Compute: Technology Competition with China</h3>
      <p>Past Event</p></div>
  </article>
  <article class="group">
    <a class="absolute inset-0" href="/events/korea-defense-strategy"></a>
    <div><h3>Korea's Defense Strategy and the U.S.-Korea Alliance</h3></div>
  </article>
  <article class="group">
    <a class="absolute inset-0" href="/events/ai-chips-compute-technology-competition-china"></a>
    <div><h3>AI, Chips, and Compute: Technology Competition with China</h3></div>
  </article>
  <article class="group"><div><h3>No link here</h3></div></article>
</div>
"""

DETAIL = """
<html><body><div class="event-header">
  <h1>AI, Chips, and Compute: Technology Competition with China</h1>
  <p class="date">December 9, 2025 | 12:00 PM</p>
</div></body></html>
"""


def test_listing_parses_cards_dedupes_and_skips_linkless():
    cands = parse_hudson_listing(LISTING)
    slugs = [c["slug"] for c in cands]
    # duplicate slug collapsed; the linkless card skipped
    assert slugs == ["ai-chips-compute-technology-competition-china", "korea-defense-strategy"]


def test_listing_detects_topics_on_title():
    by_slug = {c["slug"]: c for c in parse_hudson_listing(LISTING)}
    ai = by_slug["ai-chips-compute-technology-competition-china"]
    assert ai["topics"] == ["ai", "compute", "semiconductor"] or (
        "ai" in ai["topics"] and "semiconductor" in ai["topics"])
    assert by_slug["korea-defense-strategy"]["topics"] == []   # off-topic


def test_listing_href_resolved():
    ai = parse_hudson_listing(LISTING)[0]
    assert ai["href"] == "/events/ai-chips-compute-technology-competition-china"


def test_parse_date_from_detail():
    assert parse_hudson_date(DETAIL) == "2025-12-09"


def test_parse_date_none_when_absent():
    assert parse_hudson_date("<html><body>No date listed.</body></html>") is None
