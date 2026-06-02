import json

import aggregator.pipeline as pl
from aggregator.config import Source
from aggregator.fetchers.base import SourceResult
from aggregator.models import Event


def test_pipeline_excludes_garbage_date_end_to_end(tmp_path, monkeypatch):
    src = Source("DC2", "DC2", "luma", 1, True, url="x")
    good = Event(id="g", title="AI workshop", start="2026-06-10", source="DC2",
                 lat=38.9, lng=-77.04, topics=["ai"])
    bad = Event(id="b", title="AI", start="0202-01-01", source="DC2", topics=["ai"])

    async def fake_gather(sources):
        return [SourceResult(src, [good, bad], 200, None)]

    monkeypatch.setattr(pl, "gather_all", fake_gather)
    monkeypatch.setattr(pl, "deliver", lambda *a, **k: ("dry-run", "test"))
    pl.run(out_dir=str(tmp_path / "o"), db_path=str(tmp_path / "db.sqlite"),
           today="2026-06-02", enrich=False)
    recs = json.load(open(tmp_path / "o" / "events.json", encoding="utf-8"))
    ids = {r["id"] for r in recs}
    assert "g" in ids and "b" not in ids          # garbage date excluded end-to-end
    assert all(r.get("lat") is None or -77.6 <= r["lng"] <= -76.8 for r in recs)  # no ocean pins
