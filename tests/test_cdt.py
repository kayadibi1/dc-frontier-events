import os

from aggregator.config import Source
from aggregator.fetchers.cdt import parse_cdt_listing

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "cdt_listing.html")
SRC = Source("cdt", "CDT", "cdt", 2, True, url="https://cdt.org/events/")


def _events():
    with open(FIX, encoding="utf-8") as f:
        return parse_cdt_listing(SRC, f.read())


def test_parses_real_events():
    assert len(_events()) >= 3


def test_events_well_formed():
    for e in _events():
        assert e.id.startswith("cdt-")
        assert e.start[:4].isdigit() and len(e.start) >= 10     # ISO date or datetime
        assert e.source == "cdt"
        assert e.source_url.startswith("https://cdt.org/event/")
        assert e.organizer == "CDT"


def test_unique_ids():
    evs = _events()
    assert len({e.id for e in evs}) == len(evs)


def test_chatbots_event_has_tz_aware_start():
    evs = _events()
    cb = next((e for e in evs if "Chatbots" in e.title), None)
    assert cb is not None
    assert cb.start == "2026-06-16T12:00:00-04:00"          # tz-aware from dt-start
    assert cb.id == "cdt-how-to-protect-kids-from-chatbots-without-bans"
