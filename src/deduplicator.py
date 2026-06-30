from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx

SEEN_URLS_URL = "https://screadliao.github.io/Daily-Briefing-System/seen_urls.json"
WINDOW_DAYS = 7
DEFAULT_TIMEOUT = 10.0

_loaded_entries: dict[str, str] = {}


def load_seen_urls() -> set[str]:
    global _loaded_entries
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
            response = client.get(SEEN_URLS_URL)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        _loaded_entries = {}
        return set()
    if not isinstance(payload, dict):
        _loaded_entries = {}
        return set()

    entries: dict[str, str] = {}
    for item in payload.get("entries", []):
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        seen_at = item.get("seen_at")
        if not isinstance(url, str) or not url:
            continue
        if not isinstance(seen_at, str) or not _is_iso_date(seen_at):
            continue
        entries[url] = seen_at

    _loaded_entries = _prune_entries(entries, _utc_today())
    return set(_loaded_entries)


def save_seen_urls(seen: set[str], new_articles: list[dict], site_dir: Path) -> None:
    global _loaded_entries
    today = _utc_today()
    entries = _prune_entries(dict(_loaded_entries), today)

    for url in seen:
        if url:
            entries.setdefault(url, today.isoformat())

    for article in new_articles:
        url = article.get("url")
        if isinstance(url, str) and url:
            entries[url] = today.isoformat()

    site_dir.mkdir(parents=True, exist_ok=True)
    output_path = site_dir / "seen_urls.json"
    payload = {
        "entries": [
            {"url": url, "seen_at": seen_at}
            for url, seen_at in sorted(entries.items())
        ]
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _loaded_entries = entries


def _utc_today() -> datetime.date:
    return datetime.utcnow().date()


def _is_iso_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _prune_entries(entries: dict[str, str], today) -> dict[str, str]:
    cutoff = today - timedelta(days=WINDOW_DAYS - 1)
    pruned: dict[str, str] = {}
    for url, seen_at in entries.items():
        try:
            seen_date = datetime.strptime(seen_at, "%Y-%m-%d").date()
        except ValueError:
            continue
        if seen_date >= cutoff:
            pruned[url] = seen_at
    return pruned
