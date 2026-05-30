import asyncio

from aggregator.config import Source
from aggregator.enrich import enrich_layer2, extract_speakers
from aggregator.models import Event

CSIS_HTML = """
<div class="event"><h1>Data Centers and AI</h1>
  <div class="speakers">
    <div class="speaker"><span class="speaker__name">Jensen Huang</span><span>NVIDIA</span></div>
    <div class="speaker"><span class="speaker__name">Gregory Allen</span><span>CSIS</span></div>
  </div></div>
"""

CSET_PROSE_HTML = """
<article><p>Please join CSET for a fireside chat featuring Dario Amodei and
Helen Toner, moderated by Jane Smith.</p></article>
"""


def test_extract_speakers_from_structured_nodes():
    names = extract_speakers(CSIS_HTML)
    assert "Jensen Huang" in names
    assert "Gregory Allen" in names


def test_extract_speakers_from_prose():
    names = extract_speakers(CSET_PROSE_HTML)
    assert "Dario Amodei" in names
    assert "Helen Toner" in names


def test_extract_speakers_dedupes_and_rejects_nonnames():
    html = '<div class="speaker">Register Now</div><div class="speaker">Sam Altman</div>'
    names = extract_speakers(html)
    assert "Sam Altman" in names
    assert "Register Now" not in names   # not a person name


def test_extract_speakers_empty_when_none():
    assert extract_speakers("<p>No speakers listed here.</p>") == []


def test_enrich_layer2_sets_speakers():
    events = [
        Event(id="csis-1", title="AI Talk", start="2026-06-01", source="csis",
              source_url="https://www.csis.org/events/ai-talk"),
        Event(id="dc2-1", title="Meetup", start="2026-06-01", source="DC2"),  # L1: skipped
    ]
    layer = {"csis": 2, "DC2": 1}

    async def fake_fetch(url, kind):
        return '<div class="speaker"><span class="name">Sam Altman</span></div>'

    asyncio.run(enrich_layer2(events, layer, fake_fetch))
    assert events[0].speakers == ["Sam Altman"]
    assert events[1].speakers == []          # Layer-1 event untouched


def test_enrich_layer2_tolerates_fetch_failure():
    events = [Event(id="csis-2", title="X", start="2026-06-01", source="csis",
                    source_url="https://www.csis.org/events/x")]

    async def boom(url, kind):
        raise RuntimeError("network down")

    n = asyncio.run(enrich_layer2(events, {"csis": 2}, boom))
    assert n == 0 and events[0].speakers == []   # best-effort, no crash
