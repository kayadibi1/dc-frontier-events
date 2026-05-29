from aggregator.filter import apply_filters, is_dc_relevant
from aggregator.models import Event


def mk(**kw):
    base = dict(id="x", title="t", start="2026-06-10T23:00:00+00:00", source="DC2")
    base.update(kw)
    return Event(**base)


def test_dc_ontopic_event_kept():
    ev = mk(title="Machine Learning Workshop", topics=["ml"], lat=38.9, lng=-77.03)
    kept, stats = apply_filters([ev])
    assert len(kept) == 1
    assert not kept[0].is_big_name


def test_non_dc_event_dropped_on_location():
    # San Francisco coords, non-curated global calendar -> excluded.
    ev = mk(title="AI Meetup", topics=["ai"], lat=37.77, lng=-122.41, source="ai")
    kept, stats = apply_filters([ev])
    assert kept == []
    assert stats["dropped_location"] == 1


def test_big_name_flagged_and_kept_even_without_topic():
    ev = mk(title="Fireside chat with Anthropic", topics=[], lat=38.9, lng=-77.03)
    kept, stats = apply_filters([ev])
    assert len(kept) == 1
    assert kept[0].is_big_name
    assert stats["big_name"] == 1
    assert any(t == "big:Anthropic" for t in kept[0].topics)


def test_dc_offtopic_event_dropped_on_topic():
    ev = mk(title="Morning Yoga in the Park", topics=[], lat=38.9, lng=-77.03)
    kept, stats = apply_filters([ev])
    assert kept == []
    assert stats["dropped_topic"] == 1


def test_big_name_precision_no_false_positives():
    # Common DC/event phrases that must NOT trip the big-name flag.
    for text in ["Metadata management for AI teams",
                 "Arms control and AI policy panel",
                 "Intelligence community AI briefing",
                 "Intel community data-sharing forum",
                 "Register via Google Form for the AI workshop"]:
        ev = mk(title=text, lat=38.9, lng=-77.03, topics=["ai"])
        kept, _ = apply_filters([ev])
        assert kept and not kept[0].is_big_name, f"false positive on: {text!r}"


def test_big_name_new_watchlist_hits():
    for text in ["Qualcomm on the chip supply chain",
                 "A fireside with Satya Nadella",
                 "Scale AI and defense data",
                 "Intel's new foundry strategy"]:
        ev = mk(title=text, lat=38.9, lng=-77.03, topics=["ai"])
        kept, _ = apply_filters([ev])
        assert kept[0].is_big_name, f"missed big name in: {text!r}"


def test_dc_curated_virtual_event_is_relevant():
    ev = mk(title="Virtual AI Talk", description="Online webinar", topics=["ai"])
    assert is_dc_relevant(ev) is True


def test_inperson_nondc_geo_dropped_despite_dc_text():
    # Hampton Roads, VA: real coords ~200mi from DC, address says "VA 23462".
    # GEO is authoritative for in-person events -> dropped.
    ev = mk(title="AI Build Challenge", topics=["ai"], lat=36.80, lng=-76.20,
            address="Regent University, Virginia Beach, VA 23462", source="aic-washington")
    assert is_dc_relevant(ev) is False


def test_virtual_curated_event_with_bogus_geo_kept():
    # Online DC2 event with a junk placeholder geo (mid-Pacific) -> still kept.
    ev = mk(title="Online: Intro to AI Evals", description="Online webinar",
            topics=["ai"], lat=-8.5, lng=179.1, source="DC2")
    assert is_dc_relevant(ev) is True
