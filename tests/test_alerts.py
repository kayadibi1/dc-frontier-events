from aggregator.alerts import build_alerts
from aggregator.models import Event
from aggregator.storage import Store

TODAY = "2026-05-29"


def E(id, title, start="2026-06-01", big=False):
    return Event(id=id, title=title, start=start, source="cset",
                 source_url=f"https://x/{id}", is_big_name=big)


def test_alerts_lists_new_big_names():
    new = [E("a", "Plain AI Talk"), E("b", "Fireside with Nvidia", big=True)]
    md = build_alerts(new, [new[1]], TODAY)
    assert "New big-name events (1)" in md
    assert "Fireside with Nvidia" in md
    assert "New events since last run: 2" in md


def test_alerts_empty():
    md = build_alerts([], [], TODAY)
    assert "New big-name events (0)" in md
    assert "_None._" in md
    assert "New events since last run: 0" in md


def test_alerts_first_run_baseline_note():
    md = build_alerts([E("a", "x")], [], TODAY, first_run=True)
    assert "First run — baseline established" in md


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
