from aggregator.credentials import Credential
from aggregator.verify import build_verify_md, _verdict

TODAY = "2026-05-30"


def _c(name, provider="X", apply_url="https://x/a"):
    return Credential(name, provider, "fellowship", "competitive", True,
                      "https://x/landing", ("ai",), "n", apply_url=apply_url)


def test_verdict_blind_spot_flagged():
    v = _verdict({"ok": False, "code": 403, "deadline": None, "status": ""})
    assert "COULDN'T READ" in v and "403" in v


def test_verdict_read_deadline():
    v = _verdict({"ok": True, "code": 200, "deadline": "2026-07-01", "status": "open"})
    assert "2026-07-01" in v and "✅" in v


def test_verdict_read_status_only():
    v = _verdict({"ok": True, "code": 200, "deadline": None, "status": "open"})
    assert "open" in v and "✅" in v


def test_verdict_read_rolling():
    v = _verdict({"ok": True, "code": 200, "deadline": None, "status": ""})
    assert "rolling" in v.lower()


def test_verdict_unstable_flagged():
    v = _verdict({"ok": True, "code": 200, "deadline": None, "status": "", "unstable": True})
    assert "UNSTABLE" in v


def test_build_md_counts_and_lists_blind_spots():
    rows = [
        (_c("Readable One"), {"ok": True, "code": 200, "deadline": None, "status": "open"}),
        (_c("Blocked One", apply_url="https://x/blocked"),
         {"ok": False, "code": 403, "deadline": None, "status": ""}),
    ]
    md = build_verify_md(rows, TODAY)
    assert "# Deadline Verification Report" in md
    assert "1/2 readable, 1 blind spot(s)" in md
    # the blind spot is called out by name + url in its own section
    assert "couldn't be read" in md
    assert "Blocked One" in md and "https://x/blocked" in md
    # both programs appear in the table
    assert "Readable One" in md
