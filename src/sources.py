from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = PROJECT_ROOT / "sources.json"


def load_sources() -> dict[str, dict[str, Any]]:
    with SOURCES_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


SOURCES = load_sources()
