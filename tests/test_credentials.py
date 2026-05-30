from aggregator.credentials import (
    CREDENTIALS,
    Credential,
    credentials_dicts,
    render_credentials_md,
)


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
