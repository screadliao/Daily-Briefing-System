import json
from datetime import date

import httpx

from src import deduplicator


def test_load_seen_urls_returns_empty_on_http_error(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, url: str):
            raise httpx.ConnectError("boom")

    monkeypatch.setattr("src.deduplicator.httpx.Client", FakeClient)

    assert deduplicator.load_seen_urls() == set()


def test_load_seen_urls_prunes_old_entries(monkeypatch) -> None:
    payload = {
        "entries": [
            {"url": "https://keep.example/a", "seen_at": "2026-06-30"},
            {"url": "https://keep.example/b", "seen_at": "2026-06-24"},
            {"url": "https://drop.example/c", "seen_at": "2026-06-23"},
            {"url": "", "seen_at": "2026-06-30"},
            {"url": "https://drop.example/d", "seen_at": "bad-date"},
        ]
    }

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return payload

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, url: str) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("src.deduplicator.httpx.Client", FakeClient)
    monkeypatch.setattr("src.deduplicator._utc_today", lambda: date(2026, 6, 30))

    seen = deduplicator.load_seen_urls()

    assert seen == {"https://keep.example/a", "https://keep.example/b"}


def test_save_seen_urls_merges_and_writes_rolling_window(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("src.deduplicator._utc_today", lambda: date(2026, 6, 30))
    deduplicator._loaded_entries = {
        "https://keep.example/old": "2026-06-24",
        "https://drop.example/older": "2026-06-23",
    }

    deduplicator.save_seen_urls(
        {"https://keep.example/old"},
        [
            {"url": "https://new.example/a"},
            {"url": "https://new.example/b"},
            {"title": "missing url"},
        ],
        tmp_path,
    )

    payload = json.loads((tmp_path / "seen_urls.json").read_text(encoding="utf-8"))
    assert payload == {
        "entries": [
            {"url": "https://keep.example/old", "seen_at": "2026-06-24"},
            {"url": "https://new.example/a", "seen_at": "2026-06-30"},
            {"url": "https://new.example/b", "seen_at": "2026-06-30"},
        ]
    }
