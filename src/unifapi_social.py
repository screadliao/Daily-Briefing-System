"""Unif API integration — LinkedIn competitor and industry monitoring.

Queries LinkedIn company pages and industry topics via the Unif API HTTP endpoint.
Falls back silently when UNIFAPI_API_KEY is not set, so the system degrades gracefully.

Unif API docs: https://docs.unifapi.com
LinkedIn ops: GET /linkedin/companies/{slug}/posts, GET /linkedin/search/posts
"""
from __future__ import annotations

import os

import httpx

UNIFAPI_BASE = "https://api.unifapi.com"
DEFAULT_TIMEOUT = 15.0
RESULTS_PER_QUERY = 5

# LinkedIn URL slugs for competitor company pages
COMPETITOR_SLUGS = {
    "Hikvision": "hikvision",
    "Dahua Technology": "dahua-technology",
    "Axis Communications": "axis-communications",
    "Hanwha Vision": "hanwha-vision",
    # Uniview removed until a working LinkedIn company slug can be confirmed.
}

INDUSTRY_TOPICS = [
    "video surveillance AI",
    "IP camera industry",
    "AI vision security",
]


def _get(
    client: httpx.Client,
    api_key: str,
    path: str,
    params: dict | None = None,
) -> list[dict]:
    """GET a Unif API REST path and return result items."""
    try:
        resp = client.get(
            f"{UNIFAPI_BASE}{path}",
            headers={"Authorization": f"Bearer {api_key}"},
            params=params or {},
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.is_success:
            data = resp.json()
            items = data.get("results", data.get("data", data.get("items", [])))
            if isinstance(items, list):
                print(f"[unifapi] GET {path} → {len(items)} items")
                return items
            print(f"[unifapi] GET {path} → unexpected shape: {list(data.keys())}")
        else:
            print(f"[unifapi] GET {path} HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:
        print(f"[unifapi] GET {path} failed: {exc}")
    return []


def _item_to_article(item: dict, source_label: str, category: str = "_competitor") -> dict | None:
    """Normalise a Unif API result item into the standard article dict."""
    text = (
        item.get("text")
        or item.get("content")
        or item.get("title")
        or item.get("description")
        or ""
    ).strip()
    url = (item.get("url") or item.get("link") or "").strip()
    if not text or not url:
        return None
    return {
        "category": category,
        "source": source_label,
        "title": text[:120],
        "url": url,
        "summary": text[:300],
        "published": item.get("date") or item.get("publishedAt") or "",
    }


def search_linkedin(api_key: str | None = None) -> list[dict]:
    """Fetch LinkedIn posts for competitors and surveillance industry topics.

    Returns a list of article dicts compatible with the rest of the pipeline.
    Returns empty list if UNIFAPI_API_KEY is absent or all calls fail.
    """
    api_key = api_key or os.getenv("UNIFAPI_API_KEY")
    if not api_key:
        print("[unifapi] UNIFAPI_API_KEY not set — skipping LinkedIn")
        return []

    results: list[dict] = []

    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        # Layer 1: competitor company pages via /linkedin/companies/{slug}/posts
        for name, slug in COMPETITOR_SLUGS.items():
            items = _get(client, api_key, f"/linkedin/companies/{slug}/posts")
            for item in items[:RESULTS_PER_QUERY]:
                article = _item_to_article(item, f"linkedin:{name}", "_competitor")
                if article:
                    results.append(article)

        # Layer 2: industry topics via /linkedin/search/posts
        for topic in INDUSTRY_TOPICS:
            items = _get(
                client, api_key,
                "/linkedin/search/posts",
                {"keyword": topic},
            )
            for item in items[:RESULTS_PER_QUERY]:
                article = _item_to_article(item, f"linkedin_topic:{topic}", "_competitor")
                if article:
                    results.append(article)

    print(f"[unifapi] total LinkedIn articles: {len(results)}")
    return results
