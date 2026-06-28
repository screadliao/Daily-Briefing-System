"""Unif API integration — LinkedIn competitor and industry monitoring.

Queries LinkedIn company pages and industry topics via the Unif API HTTP endpoint.
Falls back silently when UNIFAPI_API_KEY is not set, so the system degrades gracefully.

Unif API docs: https://docs.unifapi.com
"""
from __future__ import annotations

import os
import logging

import httpx

logger = logging.getLogger(__name__)

UNIFAPI_BASE = "https://api.unifapi.com"
DEFAULT_TIMEOUT = 15.0
RESULTS_PER_QUERY = 5

COMPETITOR_COMPANIES = [
    "Hikvision",
    "Dahua Technology",
    "Axis Communications",
    "Hanwha Vision",
    "Uniview",
]

INDUSTRY_TOPICS = [
    "video surveillance AI",
    "IP camera industry",
    "AI vision security",
]


def _call_operation(
    client: httpx.Client,
    api_key: str,
    operation: str,
    params: dict,
) -> list[dict]:
    """Call a single Unif API operation and return result items."""
    try:
        resp = client.post(
            f"{UNIFAPI_BASE}/call_api",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"operation": operation, "params": params},
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", data.get("data", []))
    except Exception as exc:
        logger.debug("Unif API call failed [%s]: %s", operation, exc)
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
        return []

    results: list[dict] = []

    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        # Layer 1: competitor company pages
        for company in COMPETITOR_COMPANIES:
            items = _call_operation(
                client,
                api_key,
                operation="linkedin_company_posts",
                params={"company": company, "limit": RESULTS_PER_QUERY},
            )
            for item in items:
                article = _item_to_article(item, f"linkedin:{company}", "_competitor")
                if article:
                    results.append(article)

        # Layer 2: industry topics / hashtags
        for topic in INDUSTRY_TOPICS:
            items = _call_operation(
                client,
                api_key,
                operation="linkedin_search",
                params={"query": topic, "limit": RESULTS_PER_QUERY},
            )
            for item in items:
                article = _item_to_article(item, f"linkedin_topic:{topic}", "_competitor")
                if article:
                    results.append(article)

    return results
