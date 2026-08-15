from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from dotenv import load_dotenv

from src.blocklist import BLOCKLIST, filter_articles
from src.brave_search import search_watchlist
from src.deduplicator import load_seen_urls, normalize_url, save_seen_urls
from src.delivery import deliver
from src.fetcher import fetch_all
from src.formatter import build_sections_for_plain_text, render_plain_text, to_html_email
from src.synthesizer import _is_fallback, synthesize
from src.watchlist import POS_COMPETITOR_WATCHLIST, RETAIL_HOSPITALITY_WATCHLIST, WATCHLIST, rotate_half
from src.multi_search import search_watchlist_multi

MULTI_SEARCH_FALLBACK_THRESHOLD = int(os.getenv("MULTI_SEARCH_FALLBACK_THRESHOLD", "4"))
PROMPT_ARTICLE_LIMIT = int(os.getenv("PROMPT_ARTICLE_LIMIT", "10"))


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
    brave_articles = search_watchlist(rotate_half(WATCHLIST))
    retail_hospitality_articles = search_watchlist_with_fallback(RETAIL_HOSPITALITY_WATCHLIST)
    pos_competitor_articles = search_watchlist_with_fallback(POS_COMPETITOR_WATCHLIST)
    seen_urls = load_seen_urls()
    raw_articles, raw_filtered, raw_total = _filter_article_groups(raw_articles, seen_urls)
    brave_articles, brave_filtered, brave_total = _filter_article_list(brave_articles, seen_urls)
    retail_hospitality_articles, retail_filtered, retail_total = _filter_article_list(
        retail_hospitality_articles, seen_urls
    )
    pos_competitor_articles, pos_filtered, pos_total = _filter_article_list(
        pos_competitor_articles, seen_urls
    )
    raw_articles = {
        category: limit_articles(articles, [category.replace("_", " ")])
        for category, articles in raw_articles.items()
    }
    brave_articles = limit_articles(brave_articles, WATCHLIST)
    retail_hospitality_articles = limit_articles(retail_hospitality_articles, RETAIL_HOSPITALITY_WATCHLIST)
    pos_competitor_articles = limit_articles(pos_competitor_articles, POS_COMPETITOR_WATCHLIST)
    filtered_total = raw_filtered + brave_filtered + retail_filtered + pos_filtered
    article_total = raw_total + brave_total + retail_total + pos_total
    print(f"[dedup] filtered {filtered_total}/{article_total} articles already seen")
    briefing = synthesize(
        raw_articles,
        brave_articles,
        retail_hospitality_articles=retail_hospitality_articles,
        pos_competitor_articles=pos_competitor_articles,
    )
    if _is_fallback(briefing):
        print("[main] 偵測到 synthesize 降級 fallback（LLM 分析失敗），早報內容不完整。請檢查 API 與 PYTHONPATH 環境。", file=sys.stderr)
        return 1

    args.save_html.write_text(to_html_email(briefing), encoding="utf-8")
    args.save_html.parent.joinpath("latest.txt").write_text(
        render_plain_text(briefing), encoding="utf-8"
    )
    latest_json = {
        "date": briefing["date"],
        "headline": briefing["headline"],
        "keywords": briefing["keywords"],
        "sections": build_sections_for_plain_text(briefing),
    }
    args.save_html.parent.joinpath("latest.json").write_text(
        json.dumps(latest_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    site_dir = Path("_site")
    site_dir.mkdir(exist_ok=True)
    save_seen_urls(
        seen_urls,
        _collect_articles(
            raw_articles,
            brave_articles,
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
    seen_urls.update(normalize_url(url) for url in tuple(seen_urls) if url)
    filtered_articles: list[dict] = []
    filtered_count = 0
    total_count = len(articles)
    for article in articles:
        url = article.get("url")
        normalized = normalize_url(url) if isinstance(url, str) and url else None
        if normalized and normalized in seen_urls:
            filtered_count += 1
            continue
        if normalized:
            seen_urls.add(normalized)
        filtered_articles.append(article)
    return filtered_articles, filtered_count, total_count


def _collect_articles(
    raw_articles: dict[str, list[dict]],
    brave_articles: list[dict],
    retail_hospitality_articles: list[dict] | None = None,
    pos_competitor_articles: list[dict] | None = None,
) -> list[dict]:
    combined: list[dict] = []
    for articles in raw_articles.values():
        combined.extend(articles)
    combined.extend(brave_articles)
    combined.extend(retail_hospitality_articles or [])
    combined.extend(pos_competitor_articles or [])
    return combined


def search_watchlist_with_fallback(
    topics: list[str], threshold: int = MULTI_SEARCH_FALLBACK_THRESHOLD
) -> list[dict]:
    results = search_watchlist(topics)
    return results if len(results) >= threshold else results + search_watchlist_multi(topics)


def limit_articles(articles: list[dict], keywords: list[str], limit: int = PROMPT_ARTICLE_LIMIT) -> list[dict]:
    """Keep the most relevant, newest articles before they enter the LLM prompt."""
    normalized_keywords = [keyword.lower() for keyword in keywords if keyword.strip()]

    def score(article: dict) -> tuple[int, float]:
        text = " ".join(str(article.get(field, "")) for field in ("title", "summary")).lower()
        hits = sum(text.count(keyword) for keyword in normalized_keywords)
        published = str(article.get("published", "")).replace("Z", "+00:00")
        try:
            freshness = datetime.fromisoformat(published).timestamp()
        except ValueError:
            try:
                freshness = parsedate_to_datetime(published).timestamp()
            except (TypeError, ValueError):
                freshness = 0.0
        return hits, freshness

    return sorted(articles, key=score, reverse=True)[:limit]


if __name__ == "__main__":
    raise SystemExit(main())
