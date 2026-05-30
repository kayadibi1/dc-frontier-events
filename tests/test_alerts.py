from aggregator.alerts import big_names_in_dc, build_alerts
from aggregator.models import Event
from aggregator.storage import Store

TODAY = "2026-05-29"


def E(id, title, start="2026-06-01", big=False):
    return Event(id=id, title=title, start=start, source="cset",
                 source_url=f"https://x/{id}", is_big_name=big)


def DC(id, title, start="2026-06-01", big=True, lat=38.9, lng=-77.03,
       topics=("big:Anthropic",), venue=""):
    return Event(id=id, title=title, start=start, source="cset",
                 source_url=f"https://x/{id}", is_big_name=big, lat=lat, lng=lng,
                 topics=list(topics), venue_name=venue)


def test_alerts_lists_new_big_names():
    new = [E("a", "Plain AI Talk"), E("b", "Fireside with Nvidia", big=True)]
    md = build_alerts(new, [new[1]], TODAY)
    assert "New big-name events (1)" in md
    assert "Fireside with Nvidia" in md
    assert "New events since last run (2)" in md


def test_alerts_itemizes_all_new_events():
    # Regular (non-big-name) new events must be LISTED, not just counted, so a
    # subscriber can see what was added.
    new = [E("a", "Plain AI Talk"), E("b", "Another AI Meetup")]
    md = build_alerts(new, [], TODAY)
    assert "New events since last run (2)" in md
    assert "Plain AI Talk" in md
    assert "Another AI Meetup" in md


def test_alerts_empty():
    md = build_alerts([], [], TODAY)
    assert "New big-name events (0)" in md
    assert "_None._" in md
    assert "New events since last run (0)" in md


def test_alerts_first_run_baseline_note():
    md = build_alerts([E("a", "x")], [], TODAY, first_run=True)
    assert "First run — baseline established" in md
    # baseline run suppresses the full itemized list
    assert "full list suppressed" in md
    assert "Plain AI Talk" not in md


def test_big_in_dc_selects_inperson_upcoming_bigname():
    ev = DC("a", "Fireside with Dario Amodei", venue="CSIS HQ")
    got = big_names_in_dc([ev], TODAY)
    assert got == [ev]


def test_big_in_dc_excludes_virtual_or_geoless():
    # big-name + upcoming but NO coordinates (virtual/geo-less) -> not "in DC".
    ev = E("a", "Virtual fireside with Anthropic", big=True)
    assert big_names_in_dc([ev], TODAY) == []


def test_big_in_dc_excludes_nondc_geo():
    # big-name in San Francisco -> not in DC.
    ev = DC("a", "Anthropic SF event", lat=37.77, lng=-122.41)
    assert big_names_in_dc([ev], TODAY) == []


def test_big_in_dc_excludes_past():
    ev = DC("a", "Past Anthropic talk", start="2026-05-01")
    assert big_names_in_dc([ev], TODAY) == []


def test_big_in_dc_excludes_non_bigname():
    ev = DC("a", "Plain DC workshop", big=False, topics=("ai",))
    assert big_names_in_dc([ev], TODAY) == []


def test_big_in_dc_sorted_soonest_first():
    a = DC("a", "Later", start="2026-07-01")
    b = DC("b", "Sooner", start="2026-06-01")
    assert [e.id for e in big_names_in_dc([a, b], TODAY)] == ["b", "a"]


def test_alerts_renders_big_in_dc_section_first():
    ev = DC("a", "Fireside with Dario Amodei", venue="CSIS HQ")
    md = build_alerts([], [], TODAY, big_in_dc=[ev])
    assert "🚨 Big names in DC — in person (1)" in md
    assert "Fireside with Dario Amodei" in md
    assert "🎯 Anthropic" in md          # matched watchlist name shown
    assert "CSIS HQ" in md               # venue shown
    # the section appears before the deadlines section
    assert md.index("Big names in DC") < md.index("Application deadlines closing soon")


def test_alerts_omits_big_in_dc_section_when_empty():
    md = build_alerts([], [], TODAY, big_in_dc=[])
    assert "Big names in DC" not in md


def test_store_existing_ids_round_trip(tmp_path):
    db = str(tmp_path / "e.db")
    s = Store(db)
    assert s.existing_ids() == set()
    s.upsert_many([E("a", "x"), E("b", "y")])
    assert s.existing_ids() == {"a", "b"}
    s.close()
    # reopening the same db preserves ids (persistence across runs)
    s2 = Store(db)
    assert s2.existing_ids() == {"a", "b"}
    s2.close()
