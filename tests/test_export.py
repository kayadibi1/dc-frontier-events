import json

from selectolax.parser import HTMLParser

from aggregator.emit import write_json, write_map
from aggregator.models import Event


def sample():
    return [
        Event(id="dc2-1", title="AI Workshop", start="2026-06-10T23:00:00+00:00",
              source="DC2", source_url="https://luma.com/a", address="Arlington VA",
              lat=38.88, lng=-77.10, topics=["ai"]),
        Event(id="csis-1", title="Data Centers & AI", start="2026-06-04T14:30:00+00:00",
              source="csis", source_url="https://www.csis.org/events/x",
              is_big_name=True, lat=38.905, lng=-77.045, topics=["ai", "compute"]),
        Event(id="virt", title="Virtual Talk", start="2026-06-12", source="DC2"),  # no geo
    ]


def test_write_json_roundtrips(tmp_path):
    p = tmp_path / "events.json"
    n = write_json(sample(), str(p))
    assert n == 3
    data = json.loads(p.read_text(encoding="utf-8"))
    assert len(data) == 3
    assert {d["id"] for d in data} == {"dc2-1", "csis-1", "virt"}
    csis = next(d for d in data if d["id"] == "csis-1")
    assert csis["layer"] == 2 and csis["is_big_name"] is True
    assert next(d for d in data if d["id"] == "dc2-1")["layer"] == 1


def test_write_map_only_geo_events(tmp_path):
    p = tmp_path / "map.html"
    n = write_map(sample(), str(p))
    assert n == 2                       # virtual (no geo) excluded
    html = p.read_text(encoding="utf-8")
    assert "leaflet" in html.lower()
    assert "2 mapped / 3 total" in html
    # embedded payload holds exactly the 2 geo events
    tree = HTMLParser(html)
    assert tree.css_first("#map") is not None
    assert "Data Centers" in html and "AI Workshop" in html
    assert "Virtual Talk" not in html


def test_map_handles_empty(tmp_path):
    p = tmp_path / "m.html"
    assert write_map([], str(p)) == 0
    assert "0 mapped / 0 total" in p.read_text(encoding="utf-8")
