import asyncio

from aggregator.config import Source
from aggregator.enrich import enrich_layer2, extract_description, extract_speakers
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


def test_extract_speakers_rejects_org_affiliations():
    html = ('<div class="speaker"><span class="name">Carnegie Mellon University</span></div>'
            '<div class="speaker"><span class="name">Dario Amodei</span></div>'
            '<div class="speaker"><span class="name">Open Government Partnership</span></div>')
    names = extract_speakers(html)
    assert "Dario Amodei" in names
    assert "Carnegie Mellon University" not in names
    assert "Open Government Partnership" not in names


def test_extract_description_prefers_og_over_meta():
    html = ('<meta property="og:description" content="The og blurb is long enough '
            'to count as a real event description.">'
            '<meta name="description" content="A meta fallback that is also long enough.">')
    assert extract_description(html).startswith("The og blurb")


def test_extract_description_falls_back_to_meta_then_twitter():
    meta = '<meta name="description" content="Only a plain meta description, sufficiently long.">'
    assert extract_description(meta).startswith("Only a plain meta")
    tw = '<meta name="twitter:description" content="A twitter card description, long enough here.">'
    assert extract_description(tw).startswith("A twitter card")


def test_extract_description_skips_short_and_missing():
    # Below _MIN_DESC_CHARS (40) -> treated as junk and ignored.
    assert extract_description('<meta property="og:description" content="Events">') == ""
    assert extract_description("<html><head></head><body>no meta tags</body></html>") == ""


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


def test_enrich_layer2_fills_description_when_empty():
    ev = Event(id="csis-3", title="AI", start="2026-06-01", source="csis",
               source_url="https://www.csis.org/events/ai")

    async def fake_fetch(url, kind):
        return ('<meta property="og:description" content="A deep dive into AI compute '
                'policy and export controls in 2026.">')

    n = asyncio.run(enrich_layer2([ev], {"csis": 2}, fake_fetch))
    assert n == 1
    assert ev.description.startswith("A deep dive into AI compute policy")


def test_enrich_layer2_keeps_existing_description():
    ev = Event(id="csis-4", title="AI", start="2026-06-01", source="csis",
               source_url="https://www.csis.org/events/ai",
               description="Original listing blurb.")

    async def fake_fetch(url, kind):
        return ('<meta property="og:description" content="Meta blurb that must not '
                'overwrite the listing one.">'
                '<div class="speaker"><span class="name">Jane Roe</span></div>')

    asyncio.run(enrich_layer2([ev], {"csis": 2}, fake_fetch))
    assert ev.description == "Original listing blurb."   # not overwritten
    assert ev.speakers == ["Jane Roe"]                   # speakers still extracted


def test_enrich_layer2_tolerates_fetch_failure():
    events = [Event(id="csis-2", title="X", start="2026-06-01", source="csis",
                    source_url="https://www.csis.org/events/x")]

    async def boom(url, kind):
        raise RuntimeError("network down")

    n = asyncio.run(enrich_layer2(events, {"csis": 2}, boom))
    assert n == 0 and events[0].speakers == []   # best-effort, no crash
