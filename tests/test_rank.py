from aggregator.models import Event
from aggregator.rank import score_event, top_upcoming

TODAY = "2026-05-29"


def mk(**kw):
    base = dict(id="x", title="t", start="2026-06-10", source="DC2")
    base.update(kw)
    return Event(**base)


def test_big_name_outranks_plain():
    big = mk(topics=["ai"], is_big_name=True)
    plain = mk(topics=["ai"])
    assert score_event(big, TODAY) > score_event(plain, TODAY)


def test_upcoming_outranks_past():
    fut = mk(start="2026-06-10", topics=["ai"])
    past = mk(start="2024-01-01", topics=["ai"])
    assert score_event(fut, TODAY) > score_event(past, TODAY)


def test_more_topics_scores_higher():
    two = mk(topics=["ai", "semiconductor"])
    one = mk(topics=["ai"])
    assert score_event(two, TODAY) > score_event(one, TODAY)


def test_closer_to_dc_scores_higher():
    near = mk(topics=["ai"], lat=38.90, lng=-77.03)   # downtown DC
    far = mk(topics=["ai"], lat=39.29, lng=-76.61)    # Baltimore-ish, ~40mi
    assert score_event(near, TODAY) > score_event(far, TODAY)


def test_big_tags_dont_count_as_topics():
    # only a big: tag, no real topic -> topic component is 0
    ev = mk(topics=["big:Anthropic"], is_big_name=True)
    # equals big weight + upcoming (no topic, no geo)
    assert score_event(ev, TODAY) == 50.0 + 20.0


def test_top_upcoming_excludes_past_and_sorts_desc():
    evs = [
        mk(id="past", start="2024-01-01", topics=["ai"]),
        mk(id="low", start="2026-06-01", topics=["ai"]),
        mk(id="high", start="2026-06-01", topics=["ai", "compute"], is_big_name=True),
    ]
    top = top_upcoming(evs, TODAY, n=10)
    ids = [e.id for e in top]
    assert "past" not in ids
    assert ids[0] == "high"          # highest score first
