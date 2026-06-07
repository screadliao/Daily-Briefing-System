from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from src.blocklist import BLOCKLIST, filter_articles
from src.brave_search import search_watchlist
from src.delivery import deliver
from src.fetcher import fetch_all
from src.formatter import to_html_email
from src.synthesizer import synthesize
from src.watchlist import WATCHLIST


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate and deliver a daily briefing.")
    parser.add_argument("--dry-run", action="store_true", help="Print briefing JSON without delivery.")
    parser.add_argument(
        "--save-html",
        type=Path,
        default=Path("preview.html"),
        help="Optional output path for rendered HTML email preview.",
    )
    return parser


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"

    raw_articles = fetch_all()
    raw_articles = filter_articles(raw_articles, BLOCKLIST)
    brave_articles = search_watchlist(WATCHLIST)
    briefing = synthesize(raw_articles, brave_articles)

    args.save_html.write_text(to_html_email(briefing), encoding="utf-8")

    if args.dry_run:
        print(json.dumps(briefing, ensure_ascii=False, indent=2))
        return 0

    results = deliver(briefing)
    print(f"Delivered via: {', '.join(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
