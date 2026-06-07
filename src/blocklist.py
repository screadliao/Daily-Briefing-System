from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BLOCKLIST_FILE = PROJECT_ROOT / "blocklist.json"


def load_blocklist() -> dict[str, list[str]]:
    if not BLOCKLIST_FILE.exists():
        return {"keywords": [], "domains": []}
    with BLOCKLIST_FILE.open(encoding="utf-8") as f:
        data = json.load(f)
    return {
        "keywords": [k.lower() for k in data.get("keywords", [])],
        "domains": [d.lower() for d in data.get("domains", [])],
    }


def is_blocked(article: dict[str, str], blocklist: dict[str, list[str]]) -> bool:
    text = (article.get("title", "") + " " + article.get("summary", "")).lower()
    if any(kw in text for kw in blocklist["keywords"]):
        return True
    url = article.get("url", "").lower()
    return any(domain in url for domain in blocklist["domains"])


def filter_articles(
    raw_articles: dict[str, list[dict[str, str]]],
    blocklist: dict[str, list[str]],
) -> dict[str, list[dict[str, str]]]:
    if not blocklist["keywords"] and not blocklist["domains"]:
        return raw_articles
    return {
        category: [a for a in articles if not is_blocked(a, blocklist)]
        for category, articles in raw_articles.items()
    }


BLOCKLIST = load_blocklist()
