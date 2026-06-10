from aggregator.models import Event
from aggregator.source_prefs import encode_sources, filter_events_by_sources, normalize_sources


def test_source_preferences_normalize_and_encode():
    assert normalize_sources(["csis", "bogus", "DC2", "csis"]) == ("DC2", "csis")
    assert encode_sources(["csis"]) == "csis"
    assert encode_sources([]) == ""      # blank means all sources


def test_filter_events_by_origin_and_also_sources():
    evs = [
        Event(id="a", title="A", start="2026-06-10", source="csis"),
        Event(id="b", title="B", start="2026-06-10", source="DC2",
              raw={"also_sources": ["cset"]}),
        Event(id="c", title="C", start="2026-06-10", source="gwu"),
    ]
    assert [e.id for e in filter_events_by_sources(evs, ["cset"])] == ["b"]
    assert [e.id for e in filter_events_by_sources(evs, [])] == ["a", "b", "c"]
