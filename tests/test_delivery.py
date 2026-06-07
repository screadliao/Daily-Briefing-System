import os

from src.delivery import deliver, send_telegram


class DummyResponse:
    def raise_for_status(self) -> None:
        return None


def test_send_telegram_formats_message(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat456")
    monkeypatch.setattr("src.delivery.httpx.post", fake_post)

    send_telegram(
        {"date": "2026年06月06日 星期六", "headline": "今日頭條"},
        "https://example.com/preview.html",
    )

    assert captured["url"] == "https://api.telegram.org/bottoken123/sendMessage"
    assert "今日頭條" in captured["json"]["text"]
    assert "https://example.com/preview.html" in captured["json"]["text"]


def test_deliver_skips_telegram_without_token(monkeypatch) -> None:
    called = {"post": False}

    def fake_post(*args, **kwargs):
        called["post"] = True
        return DummyResponse()

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("DELIVERY_MODE", raising=False)
    monkeypatch.setattr("src.delivery.httpx.post", fake_post)

    results = deliver({"date": "2026年06月06日 星期六", "headline": "今日頭條"})

    assert results == []
    assert called["post"] is False
