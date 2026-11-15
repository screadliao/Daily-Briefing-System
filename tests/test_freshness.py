from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.freshness import filter_fresh_articles, filter_fresh_articles_with_audit, parse_published


NOW = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)


def test_parse_published_normalizes_iso_rfc822_and_brave_age_to_utc() -> None:
    assert parse_published("2026-09-15T20:00:00+08:00", NOW) == datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    assert parse_published("Tue, 15 Sep 2026 12:00:00 +0000", NOW) == NOW
    assert parse_published("3 hours ago", NOW) == NOW - timedelta(hours=3)


def test_filter_fresh_articles_drops_missing_invalid_and_old_dates() -> None:
    articles = [
        {"title": "fresh", "published": "1 day ago"},
        {"title": "old", "published": "3 days ago"},
        {"title": "missing"},
        {"title": "invalid", "published": "recently"},
    ]

    assert [article["title"] for article in filter_fresh_articles(articles, timedelta(hours=48), NOW)] == ["fresh"]


def test_freshness_audit_records_policy_age_and_dropped_articles() -> None:
    articles = [
        {"title": "fresh", "url": "https://example.com/fresh", "published": "1 day ago"},
        {"title": "old", "url": "https://example.com/old", "published": "3 days ago"},
        {"title": "missing", "url": "https://example.com/missing"},
    ]

    accepted, audit = filter_fresh_articles_with_audit(articles, timedelta(hours=48), "geo", NOW)

    assert accepted == [articles[0]]
    assert audit == {
        "policy": {"max_age_hours": 48},
        "input_count": 3,
        "accepted_count": 1,
        "dropped_count": 2,
        "accepted_articles": [
            {
                "category": "geo",
                "title": "fresh",
                "url": "https://example.com/fresh",
                "published": "1 day ago",
                "age_hours": 24,
            }
        ],
    }
