"""Static configuration: sources, watchlists, topic + location matchers.

Everything the pipeline keys on (which calendars to pull, what counts as
on-topic, who the "big names" are, where "DC metro" is) lives here so it can
be tuned without touching pipeline code. The big-name watchlist living in
config is mandated by GOAL.md.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    slug: str          # short id, e.g. "DC2" / "cset"
    name: str          # human label
    kind: str          # adapter kind: "luma" | "cset"
    layer: int         # 1=builder/community, 2=policy, 3=university
    dc_curated: bool   # True if the source is itself DC-scoped (trusted location)
    cal_id: str = ""   # luma calendar id, e.g. "cal-eCuIBRbS1atJOa6"
    url: str = ""      # listing page for HTML scrapers

    @property
    def ics_url(self) -> str:
        return f"https://api.lu.ma/ics/get?entity=calendar&id={self.cal_id}"


# Layer 1 — Luma builder/community calendars (native iCal subscription).
# cal_ids resolved live from each lu.ma/<slug> page.
LUMA_SOURCES = [
    Source("DC2", "DC Data & AI Events", "luma", 1, True, cal_id="cal-eCuIBRbS1atJOa6"),
    Source("DCtechevents", "Washington DC Tech Events", "luma", 1, True, cal_id="cal-0TDb3WUDzBp2DYy"),
    Source("dctech", "DC Tech & Venture Coalition", "luma", 1, True, cal_id="cal-Q37RKijUFFdzt97"),
    # AI Collective's calendar is global (SF/NYC/Chicago/... events), not DC-only:
    # ~11 of ~455 events are in DC. NOT dc_curated, so it is held to the strict
    # DC geo/text filter and only its genuinely-DC events are kept.
    Source("aic-washington", "AI Collective DC", "luma", 1, False, cal_id="cal-E74MDlDKBaeAwXK"),
    # Global AI calendar (Claude Community, Latent.Space, ...): NOT dc_curated,
    # so it is held to the strict DC location filter.
    Source("ai", "Global AI (Luma)", "luma", 1, False, cal_id="cal-nyk2WcWIv2CFmq8"),
]

# Layer 2 — policy / big-name (the high-signal tier). HTML scrape behind a WAF,
# so the adapter uses curl_cffi (browser TLS impersonation). CSET is a DC
# institution (125/500 ... NW, Washington DC) -> dc_curated.
CSET_SOURCES = [
    Source("cset", "CSET (Georgetown)", "cset", 2, True, url="https://cset.georgetown.edu/events/"),
    # CSIS HQ is in DC (1616 Rhode Island Ave NW); httpx-accessible.
    Source("csis", "CSIS", "csis", 2, True, url="https://www.csis.org/events"),
]

SOURCES = LUMA_SOURCES + CSET_SOURCES


# Topic relevance. Canonical topic -> regex (case-insensitive, word-boundaried
# for short/ambiguous tokens so "ai" does not match "email" / "html").
TOPIC_PATTERNS = {
    "ai": r"\bai\b|\bartificial intelligence\b|\ba\.i\.\b",
    "ml": r"\bml\b|\bmachine learning\b",
    "llm": r"\bllms?\b|large language model|\bgpt\b|generative ai|gen-?ai",
    "deep-learning": r"deep learning|neural network|\bnlp\b|computer vision|transformer",
    "data-science": r"data science|data scientist|\banalytics\b|data engineer|big data|\bdataset\b",
    "semiconductor": r"semiconductor|\bchips?\b|fab(rication)?\b|foundry|\btsmc\b|wafer|\basml\b",
    "compute": r"\bgpus?\b|datacenter|data center|\bcompute\b|\bcuda\b|accelerat|\bhpc\b",
    "policy": r"export control|chips act|ai policy|ai safety|ai governance|frontier model|ai regulation",
    "robotics": r"robotic|autonomous vehicle|self-driving",
}

# Big-name watchlist — orgs and people. A match sets is_big_name.
BIG_NAME_PATTERNS = {
    # orgs
    "Anthropic": r"\banthropic\b|\bclaude\b",
    "OpenAI": r"\bopenai\b|\bchatgpt\b",
    "Nvidia": r"\bnvidia\b",
    "Microsoft": r"\bmicrosoft\b",
    "Google DeepMind": r"\bdeepmind\b|google ai|\bgemini\b",
    "Meta AI": r"\bmeta ai\b|\bllama\b",
    "AMD": r"\bamd\b",
    "Intel": r"\bintel\b",
    # people
    "Dario Amodei": r"\bdario amodei\b|\bamodei\b",
    "Sam Altman": r"\bsam altman\b|\baltman\b",
    "Jensen Huang": r"\bjensen huang\b|\bjensen\b",
    "Brad Smith": r"\bbrad smith\b",
    "Jack Clark": r"\bjack clark\b",
}

# DC-metro proximity. Bounding box covers DC + close NoVA + close MD suburbs.
DC_BBOX = {"lat_min": 38.70, "lat_max": 39.20, "lng_min": -77.60, "lng_max": -76.80}

# Text fallback when there is no GEO. Specific enough to avoid false hits.
DC_TEXT_PATTERN = (
    r"washington,?\s*d\.?c\.?|\bd\.c\.\b|,\s*dc\b|\bdc\s*\d{5}\b|"
    r"\barlington\b|\balexandria\b|\bmclean\b|\btysons\b|\breston\b|"
    r"\bfairfax\b|\bbethesda\b|\brockville\b|college park|silver spring|"
    r"crystal city|rosslyn|ballston|\bvirginia\b|\bmaryland\b|,\s*va\b|,\s*md\b"
)

VIRTUAL_PATTERN = r"\bvirtual\b|\bonline\b|\bwebinar\b|\bzoom\b|livestream|live stream|\bremote\b"
