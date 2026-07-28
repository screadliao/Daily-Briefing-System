from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from src.blocklist import BLOCKLIST, filter_articles
from src.brave_search import search_watchlist
from src.deduplicator import load_seen_urls, save_seen_urls
from src.delivery import deliver
from src.fetcher import fetch_all
from src.formatter import render_plain_text, to_html_email
from src.synthesizer import synthesize
from src.watchlist import (
    POS_COMPETITOR_WATCHLIST,
    RETAIL_HOSPITALITY_WATCHLIST,
    SECURITY_ICG_COMPETITOR_WATCHLIST,
    WATCHLIST,
)


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
    retail_hospitality_articles = search_watchlist(RETAIL_HOSPITALITY_WATCHLIST)
    pos_competitor_articles = search_watchlist(POS_COMPETITOR_WATCHLIST)
    competitor_articles = search_watchlist(SECURITY_ICG_COMPETITOR_WATCHLIST)
    seen_urls = load_seen_urls()
    raw_articles, raw_filtered, raw_total = _filter_article_groups(raw_articles, seen_urls)
    brave_articles, brave_filtered, brave_total = _filter_article_list(brave_articles, seen_urls)
    retail_hospitality_articles, retail_filtered, retail_total = _filter_article_list(
        retail_hospitality_articles, seen_urls
    )
    pos_competitor_articles, pos_filtered, pos_total = _filter_article_list(
        pos_competitor_articles, seen_urls
    )
    competitor_articles, competitor_filtered, competitor_total = _filter_article_list(
        competitor_articles, seen_urls
    )
    filtered_total = raw_filtered + brave_filtered + retail_filtered + pos_filtered + competitor_filtered
    article_total = raw_total + brave_total + retail_total + pos_total + competitor_total
    print(f"[dedup] filtered {filtered_total}/{article_total} articles already seen")
    briefing = synthesize(
        raw_articles,
        brave_articles,
        competitor_articles=competitor_articles,
        retail_hospitality_articles=retail_hospitality_articles,
        pos_competitor_articles=pos_competitor_articles,
    )

    args.save_html.write_text(to_html_email(briefing), encoding="utf-8")
    args.save_html.parent.joinpath("latest.txt").write_text(
        render_plain_text(briefing), encoding="utf-8"
    )
    site_dir = Path("_site")
    site_dir.mkdir(exist_ok=True)
    save_seen_urls(
        seen_urls,
        _collect_articles(
            raw_articles,
            brave_articles,
            competitor_articles,
            retail_hospitality_articles,
            pos_competitor_articles,
        ),
        site_dir,
    )

    if args.dry_run:
        print(json.dumps(briefing, ensure_ascii=False, indent=2))
        return 0

    results = deliver(briefing)
    print(f"Delivered via: {', '.join(results)}")
    return 0


def _filter_article_groups(
    article_groups: dict[str, list[dict]],
    seen_urls: set[str],
) -> tuple[dict[str, list[dict]], int, int]:
    filtered_groups: dict[str, list[dict]] = {}
    filtered_count = 0
    total_count = 0
    for category, articles in article_groups.items():
        filtered_articles, removed, total = _filter_article_list(articles, seen_urls)
        filtered_groups[category] = filtered_articles
        filtered_count += removed
        total_count += total
    return filtered_groups, filtered_count, total_count


def _filter_article_list(
    articles: list[dict],
    seen_urls: set[str],
) -> tuple[list[dict], int, int]:
    filtered_articles: list[dict] = []
    filtered_count = 0
    total_count = len(articles)
    for article in articles:
        url = article.get("url")
        if isinstance(url, str) and url and url in seen_urls:
            filtered_count += 1
            continue
        filtered_articles.append(article)
    return filtered_articles, filtered_count, total_count


def _collect_articles(
    raw_articles: dict[str, list[dict]],
    brave_articles: list[dict],
    competitor_articles: list[dict],
    retail_hospitality_articles: list[dict] | None = None,
    pos_competitor_articles: list[dict] | None = None,
) -> list[dict]:
    combined: list[dict] = []
    for articles in raw_articles.values():
        combined.extend(articles)
    combined.extend(brave_articles)
    combined.extend(competitor_articles)
    combined.extend(retail_hospitality_articles or [])
    combined.extend(pos_competitor_articles or [])
    return combined


if __name__ == "__main__":
    raise SystemExit(main())
