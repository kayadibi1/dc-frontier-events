"""Re-runnable ground-truth check for the credentials deadline tracker.

Fetches every program's real application page via the SAME path the pipeline
uses (httpx -> curl_cffi fallback) and reports, per program: HTTP code, whether
the page was actually readable, and what was extracted. The point is to expose
blind spots: a page we couldn't read is shown as "⚠️ couldn't read", never as a
confident "no deadline". Read-only except it writes out/verify.md.

Run: python -m aggregator --verify
"""

from __future__ import annotations

import asyncio
import os
from datetime import date

from .credentials import CREDENTIALS
from .deadline_fetch import fetch_deadline_info


def _verdict(info: dict) -> str:
    if not info.get("ok"):
        return f"⚠️ COULDN'T READ (HTTP {info.get('code')})"
    if info.get("unstable"):
        return "⚠️ UNSTABLE — signal didn't reproduce on re-fetch; verify manually"
    if info.get("deadline"):
        return f"✅ read — deadline {info['deadline']}"
    if info.get("status"):
        return f"✅ read — applications {info['status']}"
    return "✅ read — no date/status posted (rolling)"


def build_verify_md(rows: list[tuple], today_iso: str) -> str:
    n_read = sum(1 for _, i in rows if i.get("ok"))
    n_blind = len(rows) - n_read
    out = ["# Deadline Verification Report",
           f"_Generated {today_iso}. Each program's page was fetched the same way "
           f"the pipeline does. {n_read}/{len(rows)} readable, {n_blind} blind spot(s)._",
           "",
           "| Program | Provider | HTTP | Verdict |",
           "|---|---|---|---|"]
    for c, info in rows:
        out.append(f"| {c.name} | {c.provider} | {info.get('code')} | {_verdict(info)} |")
    out.append("")
    if n_blind:
        out += [f"## ⚠️ {n_blind} page(s) couldn't be read — verify by hand", ""]
        for c, info in rows:
            if not info.get("ok"):
                out.append(f"- **{c.name}** — {c.scrape_url}")
        out.append("")
    return "\n".join(out) + "\n"


def run_verify(today_iso: str | None = None, out_dir: str = "out") -> dict:
    # The report uses ✅/⚠️; a legacy Windows console (cp1252) can't encode them
    # and would crash mid-print. Make stdout tolerant rather than strip the marks.
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    today = today_iso or date.today().isoformat()
    info = asyncio.run(fetch_deadline_info([c.scrape_url for c in CREDENTIALS], today))
    rows = [(c, info[c.scrape_url]) for c in CREDENTIALS]
    print(f"\nDeadline verification — {today}\n")
    for c, i in rows:
        print(f"  {_verdict(i):44s} {c.name}")
    n_read = sum(1 for _, i in rows if i.get("ok"))
    n_blind = len(rows) - n_read
    print(f"\n  {n_read}/{len(rows)} readable, {n_blind} blind spot(s)")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "verify.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_verify_md(rows, today))
    print(f"  wrote {path}\n")
    return {"total": len(rows), "readable": n_read, "blind": n_blind}
