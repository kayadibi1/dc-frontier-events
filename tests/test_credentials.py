from aggregator.credentials import (
    CREDENTIALS,
    Credential,
    credentials_dicts,
    render_credentials_md,
    render_deadlines_md,
    upcoming_deadlines,
)

TODAY = "2026-05-30"


def cred(name="X", deadline=None, deadline_note="", kind="fellowship"):
    return Credential(name, "Anthropic", kind, "competitive", True,
                      "https://example.com/x", ("ai",), "note",
                      deadline=deadline, deadline_note=deadline_note)


def test_all_entries_well_formed():
    assert len(CREDENTIALS) >= 8
    for c in CREDENTIALS:
        assert c.name and c.provider
        assert c.kind in {"course", "workshop", "cert", "fellowship", "access"}
        assert c.cost in {"free", "paid", "exam-fee", "competitive"}
        assert c.url.startswith("https://")
        assert isinstance(c.topics, tuple) and c.topics


def test_marquee_providers_present():
    provs = {c.provider for c in CREDENTIALS}
    assert "Anthropic" in provs
    assert "OpenAI" in provs


def test_prestige_flag():
    anthropic = next(c for c in CREDENTIALS if c.provider == "Anthropic")
    assert anthropic.prestige is True


def test_dicts_serializable():
    d = credentials_dicts()
    assert len(d) == len(CREDENTIALS)
    assert isinstance(d[0]["topics"], list)
    assert "prestige" in d[0] and "url" in d[0]


def test_render_md_groups_and_links():
    md = render_credentials_md()
    assert md.startswith("# Prestige Credentials")
    assert "Anthropic" in md and "OpenAI" in md
    # every credential's URL appears in the rendered output
    for c in CREDENTIALS:
        assert c.url in md
    # certificate marker shown for cert-bearing entries
    assert "certificate" in md


# --- funding / scholarships (backlog idea #5) ---

def test_every_live_credential_has_funding_note():
    # Each program should tell the user how to do it for free / subsidized.
    for c in CREDENTIALS:
        assert c.funding, f"missing funding note: {c.name}"


def test_free_courses_say_free():
    hf = next(c for c in CREDENTIALS if c.provider == "Hugging Face")
    assert "free" in hf.funding.lower()


def test_fellowships_marked_funded():
    for name in ("Anthropic Fellows Program", "OpenAI Residency"):
        c = next(x for x in CREDENTIALS if x.name == name)
        assert "fund" in c.funding.lower() or "paid" in c.funding.lower()


def test_funding_rendered_with_marker():
    md = render_credentials_md()
    assert "💰" in md
    # a specific, real funding mechanism shows up
    assert "Financial Aid" in md


def test_funding_in_dicts():
    d = credentials_dicts()
    assert all("funding" in row for row in d)
    assert any(row["funding"] for row in d)


def test_funding_note_honest_no_fabricated_url_when_blank():
    # funding_url is optional; when blank the render must not emit a broken link.
    md = render_credentials_md()
    assert "[funding]()" not in md


# --- credentials HTML subpage (events.emersus.ai/credentials.html) ---

from aggregator.credentials import render_credentials_html


def test_render_credentials_html_basic():
    html = render_credentials_html(credentials_dicts(), TODAY)
    assert "<!DOCTYPE html>" in html
    assert "Prestige Credentials" in html
    assert "back to events" in html                 # link home
    assert "Anthropic Fellows Program" in html      # a known program
    assert "💰" in html                              # funding surfaced
    assert "badge" in html                          # status badge present


def test_render_credentials_html_has_home_screen_icon_links():
    html = render_credentials_html(credentials_dicts(), TODAY)
    assert 'rel="apple-touch-icon" href="/apple-touch-icon.png"' in html
    assert 'rel="manifest" href="/site.webmanifest"' in html


def test_render_credentials_html_open_status_badge():
    creds = [{"name": "Fellows", "provider": "Anthropic", "kind": "fellowship",
              "cost": "competitive", "cert": True, "url": "https://x",
              "topics": ["ai"], "note": "n", "deadline": None,
              "deadline_note": "cohort-based", "apply_url": "https://x/apply",
              "app_status": "open", "funding": "Funded", "funding_url": "", "prestige": True}]
    html = render_credentials_html(creds, TODAY)
    assert "Applications open now" in html
    assert 'href="https://x/apply"' in html          # links the apply page


def test_render_credentials_html_dated_deadline_badge():
    creds = [{"name": "Y", "provider": "OpenAI", "kind": "fellowship",
              "cost": "competitive", "cert": True, "url": "https://y", "topics": ["ai"],
              "note": "n", "deadline": "2026-08-01", "deadline_note": "", "apply_url": "",
              "app_status": "", "funding": "", "funding_url": "", "prestige": True}]
    html = render_credentials_html(creds, "2026-05-30")
    assert "Apply by 2026-08-01" in html


def test_render_credentials_html_escapes_and_no_funding_ok():
    # no funding -> no 💰 line for that item; renders without error
    creds = [{"name": "Plain & Co", "provider": "X", "kind": "course", "cost": "free",
              "cert": False, "url": "https://z", "topics": [], "note": "",
              "deadline": None, "deadline_note": "anytime", "apply_url": "",
              "app_status": "", "funding": "", "funding_url": "", "prestige": False}]
    html = render_credentials_html(creds, TODAY)
    assert "Plain &amp; Co" in html                  # HTML-escaped


# --- deadline tracking ---

def test_no_fabricated_dates_in_live_list():
    # Honesty guard: nothing in the curated list carries an invented concrete
    # date (none is publicly verified). All deadlines are status-only for now.
    assert all(c.deadline is None for c in CREDENTIALS)
    # ...but each still has an honest status note.
    assert all(c.deadline_note for c in CREDENTIALS)


def test_url_fixes_applied():
    fellows = next(c for c in CREDENTIALS if c.name == "Anthropic Fellows Program")
    assert fellows.url == "https://www.anthropic.com/research/fellows-program"
    # the old broken path must not linger
    assert not any(c.url.endswith("/fellows-program") and "research" not in c.url
                   for c in CREDENTIALS)


def test_days_until():
    assert cred(deadline="2026-06-09").days_until(TODAY) == 10
    assert cred(deadline="2026-05-30").days_until(TODAY) == 0
    assert cred(deadline=None).days_until(TODAY) is None


def test_upcoming_deadlines_window_and_sort():
    items = [
        cred("soon", deadline="2026-06-15"),    # 16 days -> in
        cred("today", deadline="2026-05-30"),   # 0 days -> in
        cred("far", deadline="2026-09-01"),     # ~94 days -> out (>60)
        cred("past", deadline="2026-05-01"),    # negative -> out
        cred("rolling", deadline=None),         # no date -> out
    ]
    got = upcoming_deadlines(TODAY, within_days=60, creds=items)
    assert [c.name for c, _ in got] == ["today", "soon"]   # sorted ascending
    assert got[0][1] == 0 and got[1][1] == 16


def test_render_deadlines_live_all_rolling():
    # Live data is all rolling -> closing-soon empty, everything under rolling.
    md = render_deadlines_md(TODAY)
    assert "# Application Deadlines" in md
    assert "Closing soon" in md
    assert "_None with a verified date in range._" in md
    assert "Rolling / anytime / check page (11)" in md
    # honest statuses surfaced
    assert "enroll anytime" in md and "cohort-based" in md


def test_render_deadlines_dated_entry_shows_urgency(monkeypatch):
    import aggregator.credentials as C
    dated = [cred("Apply Now Fellowship", deadline="2026-06-05"),  # 6 days -> urgent
             cred("Rolling One", deadline=None, deadline_note="check page")]
    monkeypatch.setattr(C, "CREDENTIALS", dated)
    md = C.render_deadlines_md(TODAY)
    assert "Closing soon (within 60 days) (1)" in md
    assert "Apply Now Fellowship" in md
    assert "2026-06-05" in md and "(6 days)" in md
    assert "Rolling One" in md  # still listed under rolling
