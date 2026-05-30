"""Prestige credentials & access programs — the 'come away with proof' track.

A curated, hand-vetted shortlist of official courses, certificates, hands-on
workshops, pro certifications, and fellowship/access programs from prestigious
AI orgs. This is the HYBRID approach's curated core: these orgs mostly lack clean
machine-readable feeds, so we maintain a trustworthy list rather than scrape
fragile pages. Every URL here was confirmed live (HTTP 200) on 2026-05-30.

Unlike events, credentials are not DC-located or date-bound — they're
enroll-anytime online programs — so they ride their own track (credentials.md /
credentials.json + a digest section), NOT the DC event pipeline.

`note`/`cost`/`cert` reflect best-known details; always confirm current specifics
at the URL.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# kind: course | workshop | cert | fellowship | access
# cost: free | paid | exam-fee | competitive
PRESTIGE_PROVIDERS = {"Anthropic", "OpenAI", "NVIDIA", "Google", "Hugging Face",
                      "Microsoft", "AWS", "DeepLearning.AI"}


@dataclass(frozen=True)
class Credential:
    name: str
    provider: str
    kind: str
    cost: str
    cert: bool          # does completing it yield a certificate/credential?
    url: str
    topics: tuple
    note: str = ""

    @property
    def prestige(self) -> bool:
        return self.provider in PRESTIGE_PROVIDERS


# Curated list. Ordered roughly by prestige + résumé value. URLs verified 200.
CREDENTIALS = [
    Credential("AI Fluency / Build with Claude", "Anthropic", "course", "free", True,
               "https://www.anthropic.com/learn", ("ai", "llm"),
               "Anthropic's own courses incl. AI Fluency (certificate)."),
    Credential("OpenAI Academy", "OpenAI", "course", "free", True,
               "https://academy.openai.com/", ("ai", "llm"),
               "Free courses from OpenAI; certificates rolling out."),
    Credential("Hugging Face Courses (LLM, Agents, NLP)", "Hugging Face", "course", "free", True,
               "https://huggingface.co/learn", ("ai", "llm", "ml"),
               "Free, hands-on, certificate on completion."),
    Credential("NVIDIA Deep Learning Institute", "NVIDIA", "workshop", "paid", True,
               "https://www.nvidia.com/en-us/training/", ("ai", "ml", "compute"),
               "Instructor-led + self-paced; certificate of competency. Some virtual."),
    Credential("DeepLearning.AI Specializations", "DeepLearning.AI", "course", "paid", True,
               "https://www.deeplearning.ai/courses/", ("ai", "ml", "llm"),
               "Andrew Ng's courses; audit free, Coursera certificate paid."),
    Credential("Google AI Essentials", "Google", "course", "paid", True,
               "https://grow.google/ai-essentials/", ("ai",),
               "Beginner cert via Coursera."),
    Credential("AWS Certified AI Practitioner", "AWS", "cert", "exam-fee", True,
               "https://aws.amazon.com/certification/certified-ai-practitioner/", ("ai", "compute"),
               "Industry-recognized professional certification (proctored exam)."),
    Credential("Azure AI Engineer Associate", "Microsoft", "cert", "exam-fee", True,
               "https://learn.microsoft.com/en-us/credentials/certifications/azure-ai-engineer/",
               ("ai", "compute"), "Microsoft professional certification."),
    Credential("Google Cloud Professional ML Engineer", "Google", "cert", "exam-fee", True,
               "https://cloud.google.com/learn/certification/machine-learning-engineer",
               ("ai", "ml", "compute"), "Advanced GCP professional certification."),
    Credential("Anthropic Fellows Program", "Anthropic", "fellowship", "competitive", True,
               "https://www.anthropic.com/fellows-program", ("ai", "policy"),
               "Competitive research fellowship; stipend. Highly selective."),
    Credential("OpenAI Residency", "OpenAI", "fellowship", "competitive", True,
               "https://openai.com/residency/", ("ai", "ml"),
               "Paid pathway into AI research/engineering at OpenAI."),
]


def credentials_dicts() -> list[dict]:
    out = []
    for c in CREDENTIALS:
        d = asdict(c)
        d["topics"] = list(c.topics)
        d["prestige"] = c.prestige
        out.append(d)
    return out


_KIND_LABEL = {"course": "📘 course", "workshop": "🔧 workshop", "cert": "🎓 cert",
               "fellowship": "🏅 fellowship", "access": "🔑 access"}


def render_credentials_md() -> str:
    """Markdown for the credentials track: grouped by kind, prestige starred."""
    out = ["# Prestige Credentials & Programs",
           "_Official courses, certificates, and programs from leading AI orgs — "
           "earn proof, not just attendance. Confirm current details at each link._", ""]
    order = ["course", "cert", "workshop", "fellowship", "access"]
    by_kind: dict[str, list[Credential]] = {}
    for c in CREDENTIALS:
        by_kind.setdefault(c.kind, []).append(c)
    for kind in order:
        items = by_kind.get(kind, [])
        if not items:
            continue
        out.append(f"## {_KIND_LABEL.get(kind, kind)} ({len(items)})")
        for c in items:
            star = "⭐ " if c.prestige else ""
            # 'certificate' label only where it literally applies; a fellowship
            # /residency is itself the credential, not a certificate.
            cert = " · certificate" if (c.cert and c.kind != "fellowship") else ""
            out.append(f"- {star}**{c.name}** — {c.provider} · {c.cost}{cert}  ")
            out.append(f"  {c.note} [{c.url}]({c.url})")
        out.append("")
    return "\n".join(out) + "\n"
