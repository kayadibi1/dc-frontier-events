from aggregator.deadline_fetch import extract_deadline
from aggregator.credentials import apply_fetched_deadlines, Credential

TODAY = "2026-05-30"


def test_keyword_then_date_future():
    html = "<p>Applications close June 15, 2026 for the next cohort.</p>"
    assert extract_deadline(html, TODAY) == "2026-06-15"


def test_apply_by_phrase():
    html = "Apply by July 1, 2026 to be considered."
    assert extract_deadline(html, TODAY) == "2026-07-01"


def test_date_then_keyword():
    html = "The date 08/20/2026 is the application deadline."
    assert extract_deadline(html, TODAY) == "2026-08-20"


def test_expired_date_rejected():
    # the real-world trap: an archived page says "apply by January 20, 2025"
    html = "<p>Fellows program: apply by January 20, 2025.</p>"
    assert extract_deadline(html, TODAY) is None


def test_soonest_future_when_multiple():
    html = ("applications close September 1, 2026 ... earlier deadline "
            "June 10, 2026 ... apply by August 5, 2026")
    assert extract_deadline(html, TODAY) == "2026-06-10"


def test_date_without_keyword_ignored():
    # a bare date not next to a deadline keyword must NOT be taken
    html = "<p>Our conference is on December 25, 2026. Have a great year!</p>"
    assert extract_deadline(html, TODAY) is None


def test_abbreviated_month():
    assert extract_deadline("Apply by Dec 3, 2026.", TODAY) == "2026-12-03"


def test_no_date_returns_none():
    assert extract_deadline("<p>Enroll anytime, self-paced.</p>", TODAY) is None


def test_apply_fetched_deadlines_merges_by_url():
    creds = [
        Credential("A", "Anthropic", "fellowship", "competitive", True,
                   "https://x/a", ("ai",), "n", deadline=None, deadline_note="rolling"),
        Credential("B", "OpenAI", "course", "free", True,
                   "https://x/b", ("ai",), "n", deadline=None, deadline_note="anytime"),
    ]
    merged = apply_fetched_deadlines({"https://x/a": "2026-07-01"}, creds)
    by_name = {c.name: c for c in merged}
    assert by_name["A"].deadline == "2026-07-01"
    assert "auto-detected" in by_name["A"].deadline_note
    assert by_name["B"].deadline is None          # untouched
    assert by_name["B"].deadline_note == "anytime"


# --- application open/closed status + combined info + JSON deadline ---
from aggregator.deadline_fetch import extract_app_status, extract_info
from aggregator.credentials import apply_fetched_info, open_applications, Credential


def test_status_open():
    assert extract_app_status("<p>Applications are now open! Apply today.</p>") == "open"
    assert extract_app_status("Apply now for the 2026 cohort") == "open"


def test_status_closed_wins():
    # explicit close beats a stray 'apply'
    assert extract_app_status("Applications have closed; apply next year") == "closed"


def test_status_none():
    assert extract_app_status("<p>Self-paced course, enroll anytime.</p>") == ""


def test_extract_info_combines_json_deadline():
    html = '<script>{"applicationDeadline":"2026-07-15T00:00:00Z"}</script> apply now'
    info = extract_info(html, "2026-05-30")
    assert info["deadline"] == "2026-07-15"
    assert info["status"] == "open"


def test_extract_info_null_json_deadline_is_none():
    html = '{"applicationDeadline":null} applications are open'
    info = extract_info(html, "2026-05-30")
    assert info["deadline"] is None
    assert info["status"] == "open"


def test_apply_fetched_info_sets_open_status_and_note():
    creds = [Credential("Fellows", "Anthropic", "fellowship", "competitive", True,
                        "https://x/landing", ("ai",), "n",
                        deadline=None, deadline_note="cohort-based",
                        apply_url="https://x/cohort")]
    merged = apply_fetched_info({"https://x/cohort": {"deadline": None, "status": "open"}}, creds)
    c = merged[0]
    assert c.app_status == "open"
    assert "OPEN" in c.deadline_note
    assert open_applications(merged) == [c]   # surfaces as an open application


def test_apply_fetched_info_date_beats_status():
    creds = [Credential("F", "OpenAI", "fellowship", "competitive", True,
                        "https://x/l", ("ai",), "n", apply_url="https://x/jobs")]
    merged = apply_fetched_info(
        {"https://x/jobs": {"deadline": "2026-08-01", "status": "open"}}, creds)
    assert merged[0].deadline == "2026-08-01"
    # has a real date -> NOT counted as a date-less "open application"
    assert open_applications(merged) == []
