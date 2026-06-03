import os

from aggregator.config import Source
from aggregator.fetchers.nasem import parse_nasem_listing

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "nasem_listing.html")
SRC = Source("nasem", "National Academies", "nasem", 2, False,
             url="https://www.nationalacademies.org/events")


def _events():
    with open(FIX, encoding="utf-8") as f:
        return parse_nasem_listing(SRC, f.read())


def test_parses_real_events():
    assert len(_events()) >= 5


def test_events_well_formed():
    for e in _events():
        assert e.id.startswith("nasem-")
        assert e.start and len(e.start) == 10                  # ISO date
        assert e.source == "nasem"
        assert "/event/" in e.source_url
        assert e.source_url.startswith("https://www.nationalacademies.org/")
        assert e.organizer == "National Academies"


def test_unique_ids():
    evs = _events()
    assert len({e.id for e in evs}) == len(evs)


def test_ai_workshop_present_and_on_topic():
    evs = _events()
    ai = next((e for e in evs if "Artificial Intelligence in Obesity" in e.title), None)
    assert ai is not None
    assert ai.start == "2026-06-03"
    assert "ai" in ai.topics
