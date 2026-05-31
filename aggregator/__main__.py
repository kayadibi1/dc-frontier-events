"""Entry point: python -m aggregator [--out DIR] [--db PATH] [--today YYYY-MM-DD]"""

from __future__ import annotations

import argparse

from .pipeline import run


def main() -> None:
    p = argparse.ArgumentParser(
        prog="aggregator",
        description="DC AI & semiconductor event aggregator: fetch -> normalize -> "
                    "dedupe -> filter -> rank -> emit (ICS/RSS/JSON/map/digest).",
    )
    p.add_argument("--out", default="out", help="output directory for feeds (default: out)")
    p.add_argument("--db", default="data/events.db", help="SQLite path (default: data/events.db)")
    p.add_argument("--today", default=None,
                   help="override 'today' (YYYY-MM-DD) for the upcoming/ranking window")
    p.add_argument("--no-enrich", action="store_true",
                   help="skip Layer-2 detail-page speaker enrichment (faster, fewer requests)")
    p.add_argument("--verify", action="store_true",
                   help="ground-truth check: fetch each credential page and report what "
                        "was actually readable (writes out/verify.md); skips the pipeline")
    p.add_argument("--email", action="store_true",
                   help="render + deliver the weekly digest email from the existing store "
                        "(dry-run .eml unless SMTP_* is set); does NOT re-fetch")
    args = p.parse_args()
    if args.verify:
        from .verify import run_verify
        run_verify(today_iso=args.today, out_dir=args.out)
        return
    if args.email:
        from .emailer import send_weekly
        send_weekly(out_dir=args.out, db_path=args.db, today=args.today)
        return
    run(out_dir=args.out, db_path=args.db, today=args.today, enrich=not args.no_enrich)


if __name__ == "__main__":
    main()
