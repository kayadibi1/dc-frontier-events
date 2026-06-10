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
from datetime import date
from xml.sax.saxutils import escape

# kind: course | workshop | cert | fellowship | access
# cost: free | paid | exam-fee | competitive
PRESTIGE_PROVIDERS = {"Anthropic", "OpenAI", "NVIDIA", "Google", "Hugging Face",
                      "Microsoft", "AWS", "DeepLearning.AI"}

# A deadline within this many days of "today" is flagged as closing soon.
DEADLINE_ALERT_DAYS = 60


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
    # Application/registration deadline. `deadline` is an ISO date ONLY when a
    # real, verified date is known -- never a guess. When None, `deadline_note`
    # carries the honest status ("enroll anytime", "cohort-based; check page").
    deadline: str | None = None
    deadline_note: str = ""
    # `apply_url`: the real cohort/application/jobs page to SCRAPE for a date or
    # open/closed status (the public `url` is usually marketing w/o dates). Falls
    # back to `url`. `app_status` is auto-detected: "open" | "closed" | "".
    apply_url: str = ""
    app_status: str = ""
    # `funding`: an honest note on how to do this for free / with subsidy
    # (financial aid, free audit, cloud credits, employer-sponsored vouchers,
    # stipend). Empty when none is known -- never invented. `funding_url` points
    # to the specific aid/credits page when one exists.
    funding: str = ""
    funding_url: str = ""

    @property
    def scrape_url(self) -> str:
        return self.apply_url or self.url

    @property
    def prestige(self) -> bool:
        return self.provider in PRESTIGE_PROVIDERS

    def days_until(self, today_iso: str) -> int | None:
        """Days from today until the deadline, or None if no concrete date."""
        if not self.deadline:
            return None
        try:
            return (date.fromisoformat(self.deadline) - date.fromisoformat(today_iso)).days
        except ValueError:
            return None


# Curated list. Ordered roughly by prestige + résumé value. URLs verified 200
# (2026-05-30). deadline=None everywhere because no program publishes a verified
# concrete application date right now; deadline_note carries the honest status.
CREDENTIALS = [
    Credential("AI Fluency / Build with Claude", "Anthropic", "course", "free", True,
               "https://www.anthropic.com/learn", ("ai", "llm"),
               "Anthropic's own courses incl. AI Fluency (certificate).",
               deadline_note="enroll anytime (self-paced)",
               funding="Free. No cost to complete or to earn the certificate."),
    Credential("OpenAI Academy", "OpenAI", "course", "free", True,
               "https://academy.openai.com/", ("ai", "llm"),
               "Free courses from OpenAI; certificates rolling out.",
               deadline_note="enroll anytime (self-paced)",
               funding="Free. No cost."),
    Credential("Hugging Face Courses (LLM, Agents, NLP)", "Hugging Face", "course", "free", True,
               "https://huggingface.co/learn", ("ai", "llm", "ml"),
               "Free, hands-on, certificate on completion.",
               deadline_note="enroll anytime (self-paced)",
               funding="Free. No cost; the certificate is free too."),
    Credential("NVIDIA Deep Learning Institute", "NVIDIA", "workshop", "paid", True,
               "https://www.nvidia.com/en-us/training/", ("ai", "ml", "compute"),
               "Instructor-led + self-paced; certificate of competency. Some virtual.",
               deadline_note="self-paced anytime; instructor-led workshops scheduled (check page)",
               funding="Some self-paced DLI courses are free; NVIDIA periodically runs "
                       "no-cost instructor-led workshops (often around GTC)."),
    Credential("DeepLearning.AI Specializations", "DeepLearning.AI", "course", "paid", True,
               "https://www.deeplearning.ai/courses/", ("ai", "ml", "llm"),
               "Andrew Ng's courses; audit free, Coursera certificate paid.",
               deadline_note="enroll anytime (self-paced)",
               funding="Audit the course content free on Coursera; Coursera Financial "
                       "Aid can waive the certificate fee if you apply."),
    Credential("Google AI Essentials", "Google", "course", "paid", True,
               "https://grow.google/ai-essentials/", ("ai",),
               "Beginner cert via Coursera.",
               deadline_note="enroll anytime (self-paced)",
               funding="Delivered via Coursera. Coursera Financial Aid can waive the fee."),
    Credential("AWS Certified AI Practitioner", "AWS", "cert", "exam-fee", True,
               "https://aws.amazon.com/certification/certified-ai-practitioner/", ("ai", "compute"),
               "Industry-recognized professional certification (proctored exam).",
               deadline_note="schedule the exam anytime",
               funding="Free digital prep on AWS Skill Builder; AWS periodically offers "
                       "exam-voucher / 50%-off retake promotions (check AWS Training events)."),
    Credential("Azure AI Engineer Associate", "Microsoft", "cert", "exam-fee", True,
               "https://learn.microsoft.com/en-us/credentials/certifications/azure-ai-engineer/",
               ("ai", "compute"), "Microsoft professional certification.",
               deadline_note="schedule the exam anytime",
               funding="Free training on Microsoft Learn; Microsoft Virtual Training Days "
                       "periodically grant a free certification-exam voucher."),
    Credential("Google Cloud Professional ML Engineer", "Google", "cert", "exam-fee", True,
               "https://cloud.google.com/learn/certification/machine-learning-engineer",
               ("ai", "ml", "compute"), "Advanced GCP professional certification.",
               deadline_note="schedule the exam anytime",
               funding="Free learning + monthly credits via Google Cloud Skills Boost "
                       "(Innovators program)."),
    Credential("Anthropic Fellows Program", "Anthropic", "fellowship", "competitive", True,
               "https://www.anthropic.com/research/fellows-program", ("ai", "policy"),
               "Competitive research fellowship; stipend. Highly selective.",
               deadline_note="cohort-based; applications open periodically; check page",
               # Program-specific page that states open/closed status + any date.
               apply_url="https://alignment.anthropic.com/2025/anthropic-fellows-program/",
               funding="Funded. Provides a stipend / covers costs (it pays you)."),
    Credential("OpenAI Residency", "OpenAI", "fellowship", "competitive", True,
               "https://openai.com/residency/", ("ai", "ml"),
               "Paid pathway into AI research/engineering at OpenAI.",
               deadline_note="cohort-based; check page for the current cycle",
               funding="Funded. A paid (salaried) position."),
]


def apply_fetched_deadlines(found: dict[str, str],
                            creds: list[Credential] | None = None) -> list[Credential]:
    """Return a new list with auto-fetched deadlines merged in by URL. `found`
    maps url -> verified-future ISO date (from deadline_fetch.fetch_deadlines).
    A fetched date wins over the curated value; the note records it was detected.
    Curated entries without a fetched date are returned unchanged."""
    from dataclasses import replace
    creds = CREDENTIALS if creds is None else creds
    out = []
    for c in creds:
        iso = found.get(c.url)
        if iso:
            out.append(replace(c, deadline=iso,
                               deadline_note=f"auto-detected from page ({iso})"))
        else:
            out.append(c)
    return out


def apply_fetched_info(found: dict[str, dict],
                       creds: list[Credential] | None = None) -> list[Credential]:
    """Merge auto-fetched {deadline, status} into the list, keyed on each
    credential's scrape_url. A fetched future date sets `deadline` (+ note); a
    detected open/closed status sets `app_status` and is reflected in the note."""
    from dataclasses import replace
    creds = CREDENTIALS if creds is None else creds
    out = []
    for c in creds:
        info = found.get(c.scrape_url)
        if not info:
            out.append(c)
            continue
        iso = info.get("deadline")
        status = info.get("status") or ""
        note = c.deadline_note
        if iso:
            note = f"auto-detected deadline ({iso})"
        elif status == "open":
            note = "✅ applications OPEN. Apply now (no date posted)"
        elif status == "closed":
            note = "applications closed. Watch for the next cycle"
        out.append(replace(c, deadline=iso or c.deadline,
                           app_status=status or c.app_status, deadline_note=note))
    return out


def credentials_dicts(creds: list[Credential] | None = None) -> list[dict]:
    out = []
    for c in (CREDENTIALS if creds is None else creds):
        d = asdict(c)
        d["topics"] = list(c.topics)
        d["prestige"] = c.prestige
        out.append(d)
    return out


def upcoming_deadlines(today_iso: str, within_days: int = DEADLINE_ALERT_DAYS,
                       creds: list[Credential] | None = None) -> list[tuple[Credential, int]]:
    """Programs whose concrete deadline is today..+within_days, soonest first.
    Only entries with a verified `deadline` date qualify (rolling/None excluded)."""
    creds = CREDENTIALS if creds is None else creds
    rows = []
    for c in creds:
        d = c.days_until(today_iso)
        if d is not None and 0 <= d <= within_days:
            rows.append((c, d))
    rows.sort(key=lambda r: r[1])
    return rows


def open_applications(creds: list[Credential] | None = None) -> list[Credential]:
    """Programs with applications detected OPEN but no concrete dated deadline
    (so they wouldn't show in upcoming_deadlines) — still worth alerting on."""
    creds = CREDENTIALS if creds is None else creds
    return [c for c in creds if c.app_status == "open" and not c.deadline]


def render_deadlines_md(today_iso: str, within_days: int = DEADLINE_ALERT_DAYS,
                        creds: list[Credential] | None = None) -> str:
    """Deadline tracker: closing-soon (dated, <= window) first, then later dated,
    then rolling/anytime. Honest: undated programs are shown with their status,
    never an invented date."""
    creds = CREDENTIALS if creds is None else creds
    soon, later, open_now, rolling = [], [], [], []
    for c in creds:
        d = c.days_until(today_iso)
        if d is None:
            (open_now if c.app_status == "open" else rolling).append(c)
        elif d < 0:
            continue  # already closed; drop from the tracker
        elif d <= within_days:
            soon.append((c, d))
        else:
            later.append((c, d))
    soon.sort(key=lambda r: r[1])
    later.sort(key=lambda r: r[1])

    out = ["# Application Deadlines & Windows",
           f"_Generated {today_iso}. Concrete dates shown only when verified; "
           "everything else lists its honest status; confirm at the link._", ""]

    out.append(f"## ⏰ Closing soon (within {within_days} days) ({len(soon)})")
    if soon:
        for c, d in soon:
            urgency = "‼️" if d <= 14 else "⏰"
            out.append(f"- {urgency} **{c.deadline}** ({d} days) · {c.name} · {c.provider}  ")
            out.append(f"  {c.note} [{c.url}]({c.url})")
    else:
        out.append("_None with a verified date in range._")

    if open_now:
        out += ["", f"## ✅ Applications OPEN now (no date posted) ({len(open_now)})"]
        for c in open_now:
            out.append(f"- **{c.name}** · {c.provider} · apply now  ")
            out.append(f"  [{c.scrape_url}]({c.scrape_url})")

    if later:
        out += ["", f"## 📅 Dated, further out ({len(later)})"]
        for c, d in later:
            out.append(f"- **{c.deadline}** ({d} days) · {c.name} · {c.provider}  ")
            out.append(f"  [{c.url}]({c.url})")

    out += ["", f"## 🔄 Rolling / anytime / check page ({len(rolling)})"]
    for c in rolling:
        out.append(f"- **{c.name}** · {c.provider} · {c.deadline_note or 'check page'}  ")
        out.append(f"  [{c.url}]({c.url})")
    out.append("")
    return "\n".join(out) + "\n"


_KIND_LABEL = {"course": "📘 course", "workshop": "🔧 workshop", "cert": "🎓 cert",
               "fellowship": "🏅 fellowship", "access": "🔑 access"}


def render_credentials_md(creds: list[Credential] | None = None) -> str:
    """Markdown for the credentials track: grouped by kind, prestige starred."""
    creds = CREDENTIALS if creds is None else creds
    out = ["# Prestige Credentials & Programs",
           "_Official courses, certificates, and programs from leading AI orgs. "
           "earn proof, not just attendance. Confirm current details at each link._", ""]
    order = ["course", "cert", "workshop", "fellowship", "access"]
    by_kind: dict[str, list[Credential]] = {}
    for c in creds:
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
            out.append(f"- {star}**{c.name}** · {c.provider} · {c.cost}{cert}  ")
            out.append(f"  {c.note} [{c.url}]({c.url})")
            if c.funding:
                fund_link = f" [funding]({c.funding_url})" if c.funding_url else ""
                out.append(f"  💰 {c.funding}{fund_link}")
        out.append("")
    return "\n".join(out) + "\n"


def _he(s) -> str:
    """Escape for HTML text + double-quoted attribute values."""
    return escape(str(s or ""), {'"': "&quot;"})


def _cred_status_html(c: dict, today_iso: str) -> str:
    """Application status / deadline badge for a credential dict (from
    credentials.json). Honest: a concrete date only when verified-future, else the
    detected open/closed status, else the rolling note."""
    deadline = c.get("deadline")
    if deadline and deadline >= today_iso:
        return f'<span class="badge soon">⏰ Apply by {_he(deadline)}</span>'
    if c.get("app_status") == "open":
        return '<span class="badge open">✅ Applications open now</span>'
    if c.get("app_status") == "closed":
        return '<span class="badge closed">Applications closed. Watch for next cycle</span>'
    return f'<span class="badge rolling">{_he(c.get("deadline_note") or "check page")}</span>'


def render_credentials_html(creds: list[dict], today_iso: str) -> str:
    """Self-contained HTML page for the curated prestige programs (courses, certs,
    workshops, fellowships) with funding notes + live application status. `creds`
    is the list of dicts from credentials.json (already merged with fetched
    deadlines/status). Links each program to its apply/details page."""
    order = ["course", "cert", "workshop", "fellowship", "access"]
    by_kind: dict[str, list[dict]] = {}
    for c in creds:
        by_kind.setdefault(c.get("kind", ""), []).append(c)

    sections = []
    for kind in order:
        items = by_kind.get(kind, [])
        if not items:
            continue
        rows = []
        for c in items:
            star = "⭐ " if c.get("prestige") else ""
            url = c.get("apply_url") or c.get("url") or ""
            name = _he(c.get("name", ""))
            name_html = (f'<a href="{_he(url)}" target="_blank" rel="noopener">{name}</a>'
                         if url else name)
            cert = " · certificate" if (c.get("cert") and kind != "fellowship") else ""
            fund = c.get("funding")
            fund_html = f'<div class="fund">💰 {_he(fund)}</div>' if fund else ""
            rows.append(
                f'<li><div class="cn">{star}<b>{name_html}</b>'
                f'<span class="prov"> · {_he(c.get("provider", ""))} · '
                f'{_he(c.get("cost", ""))}{cert}</span></div>'
                f'<div class="note">{_he(c.get("note", ""))}</div>'
                f'{fund_html}'
                f'<div class="st">{_cred_status_html(c, today_iso)}</div></li>')
        sections.append(f'<h2>{_he(_KIND_LABEL.get(kind, kind))} ({len(items)})</h2>'
                        f'<ul class="creds">{"".join(rows)}</ul>')

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<title>Prestige Credentials, Fellowships &amp; Funding</title>
<style>
body{{font-family:system-ui,Arial,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;line-height:1.5;color:#222}}
a{{color:#1a4fd0}} h1{{margin-bottom:.2rem}} h2{{margin-top:1.8rem;font-size:1.1rem}}
.sub{{color:#666}} ul.creds{{list-style:none;padding:0}}
ul.creds li{{border:1px solid #eee;border-radius:8px;padding:.7rem .9rem;margin:.6rem 0}}
.prov{{color:#666;font-weight:400}} .note{{color:#444;font-size:.92rem;margin-top:.2rem}}
.fund{{color:#1b7a3d;font-size:.9rem;margin-top:.3rem}}
.st{{margin-top:.4rem}}
.badge{{display:inline-block;font-size:.82rem;padding:2px 8px;border-radius:999px;background:#f0f0f4}}
.badge.open{{background:#e3f6e8;color:#1b7a3d}} .badge.soon{{background:#fdeede;color:#a85b00}}
.badge.closed{{background:#f6e3e3;color:#a33}}
</style></head>
<body>
<p><a href="/">← back to events</a></p>
<h1>Prestige Credentials, Fellowships &amp; Funding</h1>
<p class="sub">A hand-curated shortlist of official courses, certificates, workshops, and
fellowships from leading AI orgs. Earn proof, not just attendance. Each shows how to do
it free / funded, plus live application status. Confirm details at each link. Generated {_he(today_iso)}.</p>
{chr(10).join(sections)}
</body></html>
"""
