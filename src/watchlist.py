from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WATCHLIST_FILE = PROJECT_ROOT / "watchlist.json"


def load_watchlist() -> list[str]:
    if not WATCHLIST_FILE.exists():
        return []
    with WATCHLIST_FILE.open(encoding="utf-8") as f:
        data = json.load(f)
    return [t for t in data.get("topics", []) if isinstance(t, str) and t.strip()]


WATCHLIST = load_watchlist()
