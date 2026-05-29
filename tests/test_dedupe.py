from aggregator.dedupe import dedupe
from aggregator.models import Event


def E(id, title, start, source):
    return Event(id=id, title=title, start=start, source=source)


def test_exact_uid_collapses_across_calendars():
    evs = [
        E("evt-1", "AI Night", "2026-06-10T23:00:00+00:00", "DC2"),
        E("evt-1", "AI Night", "2026-06-10T23:00:00+00:00", "aic-washington"),
    ]
    kept, removed = dedupe(evs)
    assert len(kept) == 1
    assert removed == 1
    assert "aic-washington" in kept[0].raw.get("also_sources", [])


def test_fuzzy_title_same_day_collapses():
    evs = [
        E("evt-1", "AI/ML Project Night!", "2026-06-10T23:00:00+00:00", "DC2"),
        E("evt-2", "AI ML Project Night", "2026-06-10T18:00:00+00:00", "dctech"),
    ]
    kept, removed = dedupe(evs)
    assert len(kept) == 1
    assert removed == 1


def test_distinct_events_kept():
    evs = [
        E("evt-1", "AI Workshop", "2026-06-10T23:00:00+00:00", "DC2"),
        E("evt-2", "Semiconductor Policy Panel", "2026-06-12T23:00:00+00:00", "DC2"),
    ]
    kept, removed = dedupe(evs)
    assert len(kept) == 2
    assert removed == 0


def test_same_title_different_day_not_merged():
    evs = [
        E("evt-1", "AI Office Hours", "2026-06-10T23:00:00+00:00", "DC2"),
        E("evt-2", "AI Office Hours", "2026-06-17T23:00:00+00:00", "DC2"),
    ]
    kept, removed = dedupe(evs)
    assert len(kept) == 2
    assert removed == 0
