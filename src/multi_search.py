"""Multi-backend web search for Daily Briefing watchlists.

Adds Tavily + Exa as supplementary search backends alongside Brave, widening
coverage for the retail / hospitality / POS-competitor watchlists. Each backend
returns the same normalized dict shape as ``brave_search`` so the rest of the
pipeline is agnostic of which backend produced a result.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

TAVILY_URL = "https://api.tavily.com/search"
EXA_URL = "https://api.exa.ai/search"
DEFAULT_TIMEOUT = 12.0
RESULTS_PER_BACKEND = 4


def _tavily_search(topic: str, api_key: str) -> list[dict[str, str]]:
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            resp = client.post(
                TAVILY_URL,
                json={
                    "api_key": api_key,
                    "query": topic,
                    "max_results": RESULTS_PER_BACKEND,
                    "search_depth": "basic",
                    "include_answer": False,
                    "topic": "news",
                },
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    results: list[dict[str, str]] = []
    for item in (data.get("results") or [])[:RESULTS_PER_BACKEND]:
        url = (item.get("url") or "").strip()
        title = (item.get("title") or "").strip()
        if not url or not title:
            continue
        results.append({
            "category": "_brave",  # same category so dedup/formatting treats uniformly
            "source": f"tavily:{topic}",
            "title": title,
            "url": url,
            "summary": (item.get("content") or "").strip(),
            "published": "",  # Tavily doesn't expose age here
        })
    return results


def _exa_search(topic: str, api_key: str) -> list[dict[str, str]]:
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            resp = client.post(
                EXA_URL,
                json={
                    "query": topic,
                    "numResults": RESULTS_PER_BACKEND,
                    "useAutoprompt": True,
                    "type": "auto",
                },
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    results: list[dict[str, str]] = []
    for item in (data.get("results") or [])[:RESULTS_PER_BACKEND]:
        url = (item.get("url") or "").strip()
        title = (item.get("title") or (item.get("text") or "")[:80]).strip()
        if not url or not title:
            continue
        results.append({
            "category": "_brave",
            "source": f"exa:{topic}",
            "title": title,
            "url": url,
            "summary": (item.get("text") or "").strip()[:220],
            "published": item.get("publishedDate") or "",
        })
    return results


def search_topic_multi(topic: str) -> list[dict[str, str]]:
    """Search a topic across Tavily + Exa (Brave is handled separately)."""
    results: list[dict[str, str]] = []
    tavily_key = os.getenv("TAVILY_API_KEY")
    exa_key = os.getenv("EXA_API_KEY")
    if tavily_key:
        results.extend(_tavily_search(topic, tavily_key))
    if exa_key:
        results.extend(_exa_search(topic, exa_key))
    return results


def search_watchlist_multi(topics: list[str]) -> list[dict[str, str]]:
    """Run Tavily + Exa across a watchlist of topics."""
    if not topics:
        return []
    results: list[dict[str, str]] = []
    for topic in topics:
        results.extend(search_topic_multi(topic))
    return results
