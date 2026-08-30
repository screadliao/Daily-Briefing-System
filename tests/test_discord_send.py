import logging

from discord_send import MAX_EMBEDS, SECTION_COLORS, _format_entry, build_embeds


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
