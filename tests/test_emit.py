import feedparser
from icalendar import Calendar

from aggregator.emit import write_ics, write_rss
from aggregator.models import Event


def sample():
    return [
        Event(id="evt-1", title="AI Workshop", start="2026-06-10T23:00:00+00:00",
              source="DC2", source_url="https://luma.com/a", address="Arlington VA",
              lat=38.9, lng=-77.0, topics=["ai"]),
        Event(id="evt-2", title="Anthropic Fireside", start="2026-06-12T18:00:00+00:00",
              source="DC2", source_url="https://luma.com/b", is_big_name=True,
              topics=["ai", "big:Anthropic"]),
    ]


def test_ics_parses_with_icalendar(tmp_path):
    p = tmp_path / "events.ics"
    n = write_ics(sample(), str(p))
    assert n == 2
    cal = Calendar.from_ical(p.read_bytes())
    vevents = list(cal.walk("VEVENT"))
    assert len(vevents) == 2
    summaries = [str(c.get("summary")) for c in vevents]
    assert any("Anthropic" in s for s in summaries)
    assert any(s.startswith("★") for s in summaries)  # big-name star


def test_rss_parses_with_feedparser(tmp_path):
    p = tmp_path / "feed.xml"
    n = write_rss(sample(), str(p))
    assert n == 2
    d = feedparser.parse(p.read_bytes())
    assert d.bozo == 0           # well-formed XML
    assert len(d.entries) == 2
    assert any("Anthropic" in e.title for e in d.entries)


def test_empty_inputs_produce_valid_empty_feeds(tmp_path):
    ics = tmp_path / "e.ics"
    rss = tmp_path / "e.xml"
    assert write_ics([], str(ics)) == 0
    assert write_rss([], str(rss)) == 0
    assert Calendar.from_ical(ics.read_bytes()) is not None
    assert feedparser.parse(rss.read_bytes()).bozo == 0
