from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WATCHLIST_FILE = PROJECT_ROOT / "watchlist.json"
RETAIL_HOSPITALITY_WATCHLIST_FILE = PROJECT_ROOT / "retail_hospitality_watchlist.json"
POS_COMPETITOR_WATCHLIST_FILE = PROJECT_ROOT / "pos_competitor_watchlist.json"
SECURITY_ICG_COMPETITOR_WATCHLIST_FILE = PROJECT_ROOT / "security_icg_competitor_watchlist.json"


def load_topic_list(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return [t for t in data.get("topics", []) if isinstance(t, str) and t.strip()]


def load_watchlist() -> list[str]:
    return load_topic_list(WATCHLIST_FILE)


WATCHLIST = load_watchlist()
RETAIL_HOSPITALITY_WATCHLIST = load_topic_list(RETAIL_HOSPITALITY_WATCHLIST_FILE)
POS_COMPETITOR_WATCHLIST = load_topic_list(POS_COMPETITOR_WATCHLIST_FILE)
SECURITY_ICG_COMPETITOR_WATCHLIST = load_topic_list(SECURITY_ICG_COMPETITOR_WATCHLIST_FILE)
