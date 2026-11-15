from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

_RELATIVE_AGE = re.compile(
    r"^(?P<amount>\d+)\s*(?P<unit>minute|hour|day|week|month|year)s?\s+ago$",
    re.IGNORECASE,
)
_AGE_UNITS = {
    "minute": "minutes",
    "hour": "hours",
    "day": "days",
    "week": "weeks",
    "month": "days",
    "year": "days",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_published(value: object, now: datetime | None = None) -> datetime | None:
    """Return an aware UTC timestamp for ISO 8601, RFC 822, or Brave age text."""
    if not isinstance(value, str) or not (text := value.strip()):
        return None
    now = (now or utc_now()).astimezone(timezone.utc)
    lowered = text.lower()
    if lowered in {"just now", "now", "today"}:
        return now
    if lowered == "yesterday":
        return now - timedelta(days=1)
    match = _RELATIVE_AGE.match(lowered)
    if match:
        amount = int(match["amount"])
        unit = match["unit"].lower()
        if unit == "month":
            return now - timedelta(days=amount * 30)
        if unit == "year":
            return now - timedelta(days=amount * 365)
        return now - timedelta(**{_AGE_UNITS[unit]: amount})
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def filter_fresh_articles(
    articles: list[dict], max_age: timedelta, now: datetime | None = None
) -> list[dict]:
    return filter_fresh_articles_with_audit(articles, max_age, "", now)[0]


def filter_fresh_articles_with_audit(
    articles: list[dict], max_age: timedelta, category: str, now: datetime | None = None
) -> tuple[list[dict], dict]:
    now = (now or utc_now()).astimezone(timezone.utc)
    cutoff = now - max_age
    accepted: list[dict] = []
    accepted_articles: list[dict] = []
    for article in articles:
        published = parse_published(article.get("published"), now)
        if published is None or published < cutoff:
            continue
        accepted.append(article)
        accepted_articles.append(
            {
                "category": category,
                "title": article.get("title"),
                "url": article.get("url"),
                "published": article.get("published"),
                "age_hours": (now - published).total_seconds() / 3600,
            }
        )
    return accepted, {
        "policy": {"max_age_hours": max_age.total_seconds() / 3600},
        "input_count": len(articles),
        "accepted_count": len(accepted),
        "dropped_count": len(articles) - len(accepted),
        "accepted_articles": accepted_articles,
    }
