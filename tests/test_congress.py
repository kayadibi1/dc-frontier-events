import json
import os

from aggregator.config import Source
from aggregator.fetchers.congress import parse_congress_meeting

SRC = Source("congress", "U.S. Congress", "congress", 2, True)


def _load(n):
    p = os.path.join(os.path.dirname(__file__), "fixtures", f"congress_meeting_{n}.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def test_parses_ai_hearing():
    ev = parse_congress_meeting(SRC, _load(0), "2026-06-02")
    assert ev is not None
    assert ev.id == "congress-119338"
    assert "AI-Ready America" in ev.title
    assert not ev.title.startswith('"')                 # surrounding quotes stripped
    assert ev.start == "2026-06-03T14:15:00Z"
    assert "ai" in ev.topics
    assert "Washington, DC" in ev.address and "Rayburn" in ev.address
    assert ev.source == "congress"
    assert ev.source_url.startswith("https://www.congress.gov/")
    assert ev.speakers                                  # witnesses captured as speakers


def test_skips_past_meeting():
    assert parse_congress_meeting(SRC, _load(0), "2026-12-01") is None   # hearing already happened


def test_cancelled_meeting_skipped():
    m = dict(_load(0))
    m["meetingStatus"] = "Cancelled"
    assert parse_congress_meeting(SRC, m, "2026-06-02") is None


def test_offtopic_title_dropped():
    m = dict(_load(0))
    m["title"] = '"Agriculture, Rural Development Appropriations Markup"'
    assert parse_congress_meeting(SRC, m, "2026-06-02") is None
