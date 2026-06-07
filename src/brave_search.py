from __future__ import annotations

import os

import httpx

BRAVE_NEWS_URL = "https://api.search.brave.com/res/v1/news/search"
DEFAULT_TIMEOUT = 10.0
RESULTS_PER_TOPIC = 3


def search_topic(topic: str, api_key: str) -> list[dict[str, str]]:
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            response = client.get(
                BRAVE_NEWS_URL,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                },
                params={"q": topic, "count": RESULTS_PER_TOPIC, "freshness": "pd"},
            )
            response.raise_for_status()
            data = response.json()
    except Exception:
        return []

    results: list[dict[str, str]] = []
    for item in data.get("results", []):
        title = item.get("title", "").strip()
        url = item.get("url", "").strip()
        if not title or not url:
            continue
        results.append({
            "category": "_brave",
            "source": f"brave:{topic}",
            "title": title,
            "url": url,
            "summary": item.get("description", "").strip(),
            "published": item.get("age", ""),
        })
    return results


def search_watchlist(topics: list[str], api_key: str | None = None) -> list[dict[str, str]]:
    api_key = api_key or os.getenv("BRAVE_API_KEY")
    if not api_key or not topics:
        return []
    results: list[dict[str, str]] = []
    for topic in topics:
        results.extend(search_topic(topic, api_key))
    return results
