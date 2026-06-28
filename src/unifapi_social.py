"""Unif API integration — LinkedIn competitor and industry monitoring.

Queries LinkedIn company pages and industry topics via the Unif API HTTP endpoint.
Falls back silently when UNIFAPI_API_KEY is not set, so the system degrades gracefully.

Unif API docs: https://docs.unifapi.com
"""
from __future__ import annotations

import os

import httpx

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


def _list_operations(client: httpx.Client, api_key: str, query: str) -> list[dict]:
    """Discover available operations matching a keyword via list_operations."""
    try:
        resp = client.post(
            f"{UNIFAPI_BASE}/list_operations",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"q": query},
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.is_success:
            data = resp.json()
            ops = data.get("operations", data.get("results", data.get("data", [])))
            print(f"[unifapi] list_operations({query!r}) → {len(ops)} ops found")
            for op in ops[:10]:
                name = op.get("name") or op.get("id") or op.get("operation") or str(op)
                print(f"  • {name}")
            return ops
        print(f"[unifapi] list_operations HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:
        print(f"[unifapi] list_operations failed: {exc}")
    return []


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
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"operation": operation, "params": params},
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.is_success:
            data = resp.json()
            items = data.get("results", data.get("data", []))
            print(f"[unifapi] call_api({operation!r}) → {len(items)} items")
            return items
        print(f"[unifapi] call_api({operation!r}) HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:
        print(f"[unifapi] call_api({operation!r}) failed: {exc}")
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


def _resolve_operation_name(ops: list[dict], keywords: list[str]) -> str | None:
    """Find the best matching operation name from discovered ops list."""
    for op in ops:
        name = (op.get("name") or op.get("id") or op.get("operation") or "").lower()
        if all(kw.lower() in name for kw in keywords):
            return op.get("name") or op.get("id") or op.get("operation")
    return None


def search_linkedin(api_key: str | None = None) -> list[dict]:
    """Fetch LinkedIn posts for competitors and surveillance industry topics.

    Returns a list of article dicts compatible with the rest of the pipeline.
    Returns empty list if UNIFAPI_API_KEY is absent or all calls fail.
    On first run, discovers available LinkedIn operation names via list_operations.
    """
    api_key = api_key or os.getenv("UNIFAPI_API_KEY")
    if not api_key:
        print("[unifapi] UNIFAPI_API_KEY not set — skipping LinkedIn")
        return []

    results: list[dict] = []

    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        # Step 1: discover available LinkedIn operations
        linkedin_ops = _list_operations(client, api_key, "linkedin")

        # Resolve operation names dynamically, fall back to guesses if discovery fails
        company_posts_op = (
            _resolve_operation_name(linkedin_ops, ["company", "post"])
            or _resolve_operation_name(linkedin_ops, ["company"])
            or "linkedin/company-posts"
        )
        search_op = (
            _resolve_operation_name(linkedin_ops, ["search"])
            or "linkedin/search"
        )
        print(f"[unifapi] using ops: company={company_posts_op!r}, search={search_op!r}")

        # Layer 1: competitor company pages
        for company in COMPETITOR_COMPANIES:
            items = _call_operation(
                client, api_key,
                operation=company_posts_op,
                params={"company": company, "limit": RESULTS_PER_QUERY},
            )
            for item in items:
                article = _item_to_article(item, f"linkedin:{company}", "_competitor")
                if article:
                    results.append(article)

        # Layer 2: industry topics
        for topic in INDUSTRY_TOPICS:
            items = _call_operation(
                client, api_key,
                operation=search_op,
                params={"query": topic, "limit": RESULTS_PER_QUERY},
            )
            for item in items:
                article = _item_to_article(item, f"linkedin_topic:{topic}", "_competitor")
                if article:
                    results.append(article)

    print(f"[unifapi] total LinkedIn articles: {len(results)}")
    return results
