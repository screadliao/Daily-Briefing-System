import json
import logging
from datetime import datetime
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from discord_send import MAX_EMBEDS, SECTION_COLORS, _format_entry, build_embeds, send_embeds, write_result


def test_format_entry_flattens_markdown_link() -> None:
    assert _format_entry("[某新聞標題](https://example.com/a)") == "某新聞標題\nhttps://example.com/a"


def test_format_entry_keeps_plain_text_and_bare_url_behavior() -> None:
    assert _format_entry("純文字") == "純文字"
    assert _format_entry("某新聞 https://example.com/a") == "某新聞\nhttps://example.com/a"


def test_build_embeds_keeps_header_and_nine_sections_without_warning(caplog) -> None:
    sections = [{"key": f"section_{i}", "label": f"Section {i}", "entries": ["entry"]} for i in range(9)]
    with caplog.at_level(logging.WARNING):
        embeds = build_embeds({"sections": sections})

    assert len(embeds) == MAX_EMBEDS == 10
    assert embeds[-1]["title"] == "Section 8"
    assert not caplog.records


def test_build_embeds_logs_section_discarded_over_cap(caplog) -> None:
    sections = [{"key": f"section_{i}", "label": f"Section {i}", "entries": ["entry"]} for i in range(10)]
    with caplog.at_level(logging.WARNING):
        embeds = build_embeds({"sections": sections})

    assert len(embeds) == MAX_EMBEDS
    assert "Section 9" in caplog.text


def test_new_board_colors_are_explicit() -> None:
    assert SECTION_COLORS["retail_hospitality_ai"]
    assert SECTION_COLORS["pos_kiosk_dynamics"]


def test_send_embeds_requests_message_and_returns_message_id(monkeypatch) -> None:
    class Response:
        status = 200

        def read(self) -> bytes:
            return b'{"id": "123456789"}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    captured = {}

    def urlopen(request, timeout):
        captured["url"] = request.full_url
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    assert send_embeds("https://discord.example/webhook?thread_id=42", []) == {
        "status": 200,
        "message_id": "123456789",
    }
    assert parse_qs(urlsplit(captured["url"]).query) == {"thread_id": ["42"], "wait": ["true"]}


def test_send_embeds_keeps_http_errors_as_failures(monkeypatch) -> None:
    def urlopen(request, timeout):
        raise HTTPError(request.full_url, 400, "Bad Request", None, BytesIO(b"invalid embed"))

    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    with pytest.raises(RuntimeError, match=r"Discord webhook HTTP 400: invalid embed"):
        send_embeds("https://discord.example/webhook", [])


def test_write_result_writes_delivery_evidence_without_webhook_url(tmp_path) -> None:
    path = tmp_path / "latest.result.json"
    write_result(path, {"status": 200, "message_id": "123456789"}, 3)

    result = json.loads(path.read_text(encoding="utf-8"))
    assert result["status"] == 200
    assert result["message_id"] == "123456789"
    assert result["embeds_count"] == 3
    assert datetime.fromisoformat(result["sent_at"]).tzinfo is not None
    assert "webhook" not in json.dumps(result).lower()
