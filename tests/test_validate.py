from aggregator.models import Event
from aggregator.validate import validate_pre_filter

T = "2026-06-02"
NAMES = ["Alpha Bravo", "Charlie Delta", "Echo Foxtrot", "Golf Hotel", "India Juliet",
         "Kilo Lima", "Mike November", "Oscar Papa", "Quebec Romeo", "Sierra Tango",
         "Uniform Victor", "Whiskey Xray", "Yankee Zulu"]   # 13 digit-free names


def _ev(**kw):
    kw.setdefault("title", "x"); kw.setdefault("source", "csis"); kw.setdefault("start", "2026-06-10")
    return Event(id=kw.pop("id", "e1"), **kw)


def test_pre_excludes_implausible_date():
    clean, dropped = validate_pre_filter([_ev(start="0202-01-01")], T)
    assert clean == [] and dropped[0][1] == "date"


def test_pre_downgrades_timed_without_tz():
    ev = _ev(start="2026-06-10T11:00:00", end="2026-06-10T12:00:00", tz=None)
    clean, dropped = validate_pre_filter([ev], T)
    assert ev.start == "2026-06-10" and ev.end == "2026-06-10"
    assert any(d[1] == "time" for d in dropped)


def test_pre_drops_overlong_speaker_list_wholesale():
    ev = _ev(speakers=list(NAMES))
    validate_pre_filter([ev], T)
    assert ev.speakers == []


def test_pre_removes_junk_speakers_keeps_real():
    ev = _ev(speakers=["EDT Brought", "Arun Gupta"])
    validate_pre_filter([ev], T)
    assert ev.speakers == ["Arun Gupta"]


def test_pre_clears_address_for_pure_virtual():
    ev = _ev(address="CSIS, 1616 Rhode Island Ave NW, Washington, DC 20036",
             raw={"virtual": True})
    validate_pre_filter([ev], T)
    assert ev.address == ""


def test_pre_keeps_zipless_address():
    ev = _ev(address="Marvin Center, Washington, DC")
    validate_pre_filter([ev], T)
    assert ev.address == "Marvin Center, Washington, DC"
