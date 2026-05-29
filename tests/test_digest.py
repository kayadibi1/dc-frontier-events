from aggregator.digest import build_digest
from aggregator.models import Event

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
